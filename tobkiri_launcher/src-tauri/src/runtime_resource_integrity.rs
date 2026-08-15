//! Fail-closed verification for the packaged Python runtime tree.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub(crate) const MANIFEST_NAME: &str = "runtime-resource-manifest.v1.json";
const MANIFEST_SCHEMA: &str = "io.tobkiri.runtime-resource-manifest.v1";

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct VerifiedResourceManifest {
    sha256: String,
    entries: BTreeMap<PathBuf, ResourceEntry>,
}

impl VerifiedResourceManifest {
    pub(crate) fn sha256(&self) -> &str {
        &self.sha256
    }

    pub(crate) fn entry(&self, path: &Path) -> Option<&ResourceEntry> {
        self.entries.get(path)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ResourceManifest {
    schema: String,
    entries: Vec<ResourceEntry>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ResourceEntry {
    pub(crate) path: String,
    pub(crate) size: u64,
    pub(crate) sha256: String,
}

fn collect_files(root: &Path, current: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
    for entry in fs::read_dir(current)
        .with_context(|| format!("failed to read runtime directory {}", current.display()))?
    {
        let entry = entry?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            bail!(
                "packaged runtime resource may not be a symlink: {}",
                path.display()
            );
        }
        if metadata.is_dir() {
            if path.file_name().and_then(|name| name.to_str()) == Some("__pycache__") {
                bail!(
                    "packaged runtime may not contain Python bytecode: {}",
                    path.display()
                );
            }
            collect_files(root, &path, files)?;
        } else if metadata.is_file() && path.strip_prefix(root)? != Path::new(MANIFEST_NAME) {
            if matches!(
                path.extension().and_then(|value| value.to_str()),
                Some("pyc" | "pyo")
            ) {
                bail!(
                    "packaged runtime may not contain Python bytecode: {}",
                    path.display()
                );
            }
            files.push(path.strip_prefix(root)?.to_path_buf());
        }
    }
    Ok(())
}

pub(crate) fn verify(root: &Path) -> Result<VerifiedResourceManifest> {
    let manifest_path = root.join(MANIFEST_NAME);
    let metadata = fs::symlink_metadata(&manifest_path).with_context(|| {
        format!(
            "packaged runtime manifest is missing: {}",
            manifest_path.display()
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        bail!("packaged runtime manifest is not a regular file");
    }
    let manifest_bytes = fs::read(&manifest_path)?;
    let manifest: ResourceManifest = serde_json::from_slice(&manifest_bytes)
        .context("packaged runtime manifest is malformed")?;
    if manifest.schema != MANIFEST_SCHEMA {
        bail!("packaged runtime manifest schema is unsupported");
    }

    let mut expected = BTreeMap::new();
    let mut verified_entries = BTreeMap::new();
    for entry in manifest.entries {
        let relative = PathBuf::from(&entry.path);
        if relative.is_absolute()
            || relative.components().any(|part| {
                matches!(
                    part,
                    std::path::Component::ParentDir | std::path::Component::CurDir
                )
            })
            || expected
                .insert(relative.clone(), (entry.size, entry.sha256.clone()))
                .is_some()
        {
            bail!("packaged runtime manifest contains an unsafe or duplicate path");
        }
        verified_entries.insert(relative, entry);
    }

    let mut actual_files = Vec::new();
    collect_files(root, root, &mut actual_files)?;
    actual_files.sort();
    if actual_files != expected.keys().cloned().collect::<Vec<_>>() {
        bail!("packaged runtime file inventory does not match its manifest");
    }
    for relative in actual_files {
        let payload = fs::read(root.join(&relative))?;
        let (size, digest) = &expected[&relative];
        if payload.len() as u64 != *size || format!("{:x}", Sha256::digest(&payload)) != *digest {
            bail!(
                "packaged runtime resource failed integrity: {}",
                relative.display()
            );
        }
    }
    Ok(VerifiedResourceManifest {
        sha256: format!("{:x}", Sha256::digest(&manifest_bytes)),
        entries: verified_entries,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn fixture() -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "tobkiri-runtime-integrity-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(root.join("core_runtime")).unwrap();
        let payload = b"bootstrap\n";
        fs::write(root.join("core_runtime/bootstrap.py"), payload).unwrap();
        let manifest = serde_json::json!({
            "schema": MANIFEST_SCHEMA,
            "entries": [{
                "path": "core_runtime/bootstrap.py",
                "size": payload.len(),
                "sha256": format!("{:x}", Sha256::digest(payload)),
            }],
        });
        fs::write(
            root.join(MANIFEST_NAME),
            serde_json::to_vec(&manifest).unwrap(),
        )
        .unwrap();
        root
    }

    #[test]
    fn accepts_exact_resource_tree() {
        let root = fixture();
        assert!(verify(&root).is_ok());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_missing_extra_and_tampered_resources() {
        let missing = fixture();
        fs::remove_file(missing.join("core_runtime/bootstrap.py")).unwrap();
        assert!(verify(&missing).is_err());
        fs::remove_dir_all(missing).unwrap();

        let extra = fixture();
        fs::write(extra.join("unlisted-resource.txt"), b"unlisted\n").unwrap();
        assert!(verify(&extra).is_err());
        fs::remove_dir_all(extra).unwrap();

        let tampered = fixture();
        fs::write(tampered.join("core_runtime/bootstrap.py"), b"tampered").unwrap();
        assert!(verify(&tampered).is_err());
        fs::remove_dir_all(tampered).unwrap();

        let nested_manifest = fixture();
        fs::write(
            nested_manifest.join("core_runtime/runtime-resource-manifest.v1.json"),
            b"{}",
        )
        .unwrap();
        assert!(verify(&nested_manifest).is_err());
        fs::remove_dir_all(nested_manifest).unwrap();
    }

    #[test]
    fn rejects_python_bytecode_even_when_listed() {
        let root = fixture();
        let bytecode = b"bytecode";
        let cache = root.join("core_runtime/__pycache__");
        fs::create_dir_all(&cache).unwrap();
        fs::write(cache.join("bootstrap.pyc"), bytecode).unwrap();
        let manifest_path = root.join(MANIFEST_NAME);
        let mut manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        manifest["entries"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "path": "core_runtime/__pycache__/bootstrap.pyc",
                "size": bytecode.len(),
                "sha256": format!("{:x}", Sha256::digest(bytecode)),
            }));
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();

        assert!(verify(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlinked_resources() {
        use std::os::unix::fs::symlink;

        let root = fixture();
        let target = root.join("target.py");
        fs::write(&target, b"bootstrap\n").unwrap();
        fs::remove_file(root.join("core_runtime/bootstrap.py")).unwrap();
        symlink(&target, root.join("core_runtime/bootstrap.py")).unwrap();
        assert!(verify(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
