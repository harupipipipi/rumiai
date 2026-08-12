//! Trusted verifier and snapshotter for the packaged Defaults Python source closure.
//!
//! No Python code is imported until every declared source has been copied from
//! a digest-verified file handle into a private, link-free snapshot.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use sha2::{Digest, Sha256};

const SCHEMA: &str = "io.tobkiri.packaged-defaultspack-source.v1";
const ROOTS: &[&str] = &[
    "scripts",
    "tobkiri_protocol",
    "ecosystem/defaultspack/domain/runtime_v4",
    "ecosystem/defaultspack/v4",
    "ecosystem/defaultspack/runtime",
    "ecosystem/defaultspack/defaultspack",
];
const FILES: &[&str] = &[
    "ecosystem/defaultspack/pack.v4.json",
    "ecosystem/defaultspack/contracts.v4.json",
    "ecosystem/defaultspack/artifact-index.v4.json",
];
const MAX_MANIFEST_BYTES: u64 = 4 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 256 * 1024 * 1024;

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

#[derive(Debug, Clone)]
struct ExpectedFile {
    size: u64,
    sha256: String,
    executable: bool,
}

/// A verified source tree. Its directory is removed when the value is dropped.
#[derive(Debug)]
pub struct VerifiedSourceSnapshot {
    root: PathBuf,
}

impl VerifiedSourceSnapshot {
    pub fn root(&self) -> &Path {
        &self.root
    }
}

impl Drop for VerifiedSourceSnapshot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn exact_keys(value: &serde_json::Map<String, Value>, expected: &[&str]) -> bool {
    value.keys().map(String::as_str).collect::<BTreeSet<_>>()
        == expected.iter().copied().collect::<BTreeSet<_>>()
}

fn safe_relative(value: &str) -> bool {
    !value.is_empty()
        && !value.contains(['\\', '\0'])
        && !value.starts_with('~')
        && !Path::new(value).is_absolute()
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
        && Path::new(value).to_string_lossy().replace('\\', "/") == value
}

fn parse_manifest(bytes: &[u8]) -> io::Result<BTreeMap<String, ExpectedFile>> {
    let value: Value = serde_json::from_slice(bytes)
        .map_err(|error| invalid(format!("source manifest is malformed: {error}")))?;
    let object = value
        .as_object()
        .ok_or_else(|| invalid("source manifest must be an object"))?;
    if !exact_keys(object, &["schema", "roots", "files"]) {
        return Err(invalid("source manifest has unknown or missing fields"));
    }
    if object.get("schema").and_then(Value::as_str) != Some(SCHEMA) {
        return Err(invalid("source manifest schema marker is unknown"));
    }
    let roots = object
        .get("roots")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid("source manifest roots must be an array"))?;
    if roots.len() != ROOTS.len()
        || roots
            .iter()
            .zip(ROOTS)
            .any(|(actual, expected)| actual.as_str() != Some(expected))
    {
        return Err(invalid(
            "source manifest roots differ from the trusted closure",
        ));
    }
    let files = object
        .get("files")
        .and_then(Value::as_array)
        .filter(|files| !files.is_empty())
        .ok_or_else(|| invalid("source manifest files must be a non-empty array"))?;
    let mut expected = BTreeMap::new();
    let mut previous: Option<&str> = None;
    for value in files {
        let entry = value
            .as_object()
            .ok_or_else(|| invalid("source manifest file entry must be an object"))?;
        if !exact_keys(entry, &["path", "type", "size", "sha256", "executable"]) {
            return Err(invalid(
                "source manifest file entry has unknown or missing fields",
            ));
        }
        let path = entry
            .get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| invalid("source manifest path must be a string"))?;
        if !safe_relative(path)
            || !ROOTS
                .iter()
                .any(|root| path.starts_with(&format!("{root}/")))
                && !FILES.contains(&path)
        {
            return Err(invalid(format!(
                "source manifest path is outside the closure: {path:?}"
            )));
        }
        if previous.is_some_and(|value| value >= path) {
            return Err(invalid("source manifest paths must be unique and sorted"));
        }
        previous = Some(path);
        if entry.get("type").and_then(Value::as_str) != Some("regular-file") {
            return Err(invalid(format!(
                "source manifest type is not regular-file: {path}"
            )));
        }
        let size = entry
            .get("size")
            .and_then(Value::as_u64)
            .filter(|size| *size <= MAX_SOURCE_BYTES)
            .ok_or_else(|| invalid(format!("source manifest size is invalid: {path}")))?;
        let sha256 = entry
            .get("sha256")
            .and_then(Value::as_str)
            .filter(|digest| {
                digest.len() == 64
                    && digest
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            })
            .ok_or_else(|| invalid(format!("source manifest SHA-256 is invalid: {path}")))?;
        let executable = entry
            .get("executable")
            .and_then(Value::as_bool)
            .ok_or_else(|| {
                invalid(format!(
                    "source manifest executable flag is invalid: {path}"
                ))
            })?;
        expected.insert(
            path.to_owned(),
            ExpectedFile {
                size,
                sha256: sha256.to_owned(),
                executable,
            },
        );
    }
    Ok(expected)
}

#[cfg(unix)]
fn identity(metadata: &fs::Metadata) -> (u64, u64, u64, i64, i64) {
    use std::os::unix::fs::MetadataExt;
    (
        metadata.dev(),
        metadata.ino(),
        metadata.len(),
        metadata.mtime_nsec(),
        metadata.ctime_nsec(),
    )
}

#[cfg(not(unix))]
fn identity(metadata: &fs::Metadata) -> (u64, u64, u64, i64, i64) {
    let modified = metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map_or(0, |time| time.as_nanos() as i64);
    (0, 0, metadata.len(), modified, 0)
}

#[cfg(unix)]
fn reject_hardlink(metadata: &fs::Metadata, path: &Path) -> io::Result<()> {
    use std::os::unix::fs::MetadataExt;
    if metadata.nlink() != 1 {
        return Err(invalid(format!(
            "source closure contains a hardlink: {}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(windows)]
fn reject_hardlink(metadata: &fs::Metadata, path: &Path) -> io::Result<()> {
    use std::mem::MaybeUninit;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
    };

    if !metadata.is_file() {
        return Ok(());
    }
    let file = File::open(path)?;
    let mut information = MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), information.as_mut_ptr()) } == 0 {
        return Err(invalid(format!(
            "failed to inspect source closure links at {}: {}",
            path.display(),
            io::Error::last_os_error()
        )));
    }
    if unsafe { information.assume_init() }.nNumberOfLinks != 1 {
        return Err(invalid(format!(
            "source closure contains a hardlink: {}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn reject_hardlink(_metadata: &fs::Metadata, _path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(unix)]
fn executable(metadata: &fs::Metadata) -> bool {
    use std::os::unix::fs::PermissionsExt;
    metadata.permissions().mode() & 0o111 != 0
}

#[cfg(not(unix))]
fn executable(_metadata: &fs::Metadata) -> bool {
    false
}

fn collect_actual(root: &Path, current: &Path, actual: &mut BTreeSet<String>) -> io::Result<()> {
    let metadata = fs::symlink_metadata(current)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(invalid(format!(
            "source closure root is not a real directory: {}",
            current.display()
        )));
    }
    let mut entries = fs::read_dir(current)?.collect::<Result<Vec<_>, _>>()?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            return Err(invalid(format!(
                "source closure contains a symlink: {}",
                path.display()
            )));
        }
        if metadata.is_dir() {
            collect_actual(root, &path, actual)?;
        } else if metadata.is_file() {
            reject_hardlink(&metadata, &path)?;
            let relative = path
                .strip_prefix(root)
                .map_err(|_| invalid("source closure path escaped its root"))?
                .to_string_lossy()
                .replace('\\', "/");
            if !actual.insert(relative) {
                return Err(invalid("source closure contains a duplicate path"));
            }
        } else {
            return Err(invalid(format!(
                "source closure contains a special entry: {}",
                path.display()
            )));
        }
    }
    Ok(())
}

fn create_snapshot(parent: &Path) -> io::Result<PathBuf> {
    fs::create_dir_all(parent)?;
    let parent_metadata = fs::symlink_metadata(parent)?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err(invalid("source snapshot parent is not a real directory"));
    }
    let canonical_parent = parent.canonicalize()?;
    for attempt in 0..128_u32 {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let path = canonical_parent.join(format!(
            "packaged-source-snapshot-{}-{nonce}-{attempt}",
            std::process::id()
        ));
        match fs::create_dir(&path) {
            Ok(()) => return Ok(path),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    Err(invalid("could not create a unique source snapshot"))
}

fn copy_verified(source: &Path, target: &Path, expected: &ExpectedFile) -> io::Result<()> {
    let before = fs::symlink_metadata(source)?;
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(invalid(format!(
            "source is not a regular file: {}",
            source.display()
        )));
    }
    reject_hardlink(&before, source)?;
    if before.len() != expected.size || executable(&before) != expected.executable {
        return Err(invalid(format!(
            "source metadata differs from manifest: {}",
            source.display()
        )));
    }
    let mut input = File::open(source)?;
    let opened = input.metadata()?;
    if identity(&opened) != identity(&before) {
        return Err(invalid(format!(
            "source changed while opened: {}",
            source.display()
        )));
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)?;
    let mut digest = Sha256::new();
    let mut count = 0_u64;
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read = input.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        count = count
            .checked_add(read as u64)
            .ok_or_else(|| invalid("source size overflow"))?;
        if count > expected.size {
            return Err(invalid(format!(
                "source grew while copied: {}",
                source.display()
            )));
        }
        digest.update(&buffer[..read]);
        output.write_all(&buffer[..read])?;
    }
    output.sync_all()?;
    let after = fs::symlink_metadata(source)?;
    if after.file_type().is_symlink()
        || !after.is_file()
        || identity(&after) != identity(&before)
        || count != expected.size
        || format!("{:x}", digest.finalize()) != expected.sha256
    {
        return Err(invalid(format!(
            "source content changed or mismatched: {}",
            source.display()
        )));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(
            target,
            fs::Permissions::from_mode(if expected.executable { 0o500 } else { 0o400 }),
        )?;
    }
    Ok(())
}

fn read_manifest(path: &Path) -> io::Result<Vec<u8>> {
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MAX_MANIFEST_BYTES
    {
        return Err(invalid(
            "source manifest must be a bounded regular non-symlink file",
        ));
    }
    reject_hardlink(&metadata, path)?;
    let input = File::open(path)?;
    if identity(&input.metadata()?) != identity(&metadata) {
        return Err(invalid("source manifest changed while opened"));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    input.take(MAX_MANIFEST_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 != metadata.len() {
        return Err(invalid("source manifest size changed while read"));
    }
    let after = fs::symlink_metadata(path)?;
    if identity(&metadata) != identity(&after) {
        return Err(invalid("source manifest changed while read"));
    }
    Ok(bytes)
}

/// Verify the complete source closure and return an immutable-by-construction copy.
#[cfg(test)]
pub fn verify_and_snapshot(
    runtime_root: &Path,
    snapshot_parent: &Path,
) -> io::Result<VerifiedSourceSnapshot> {
    let manifest =
        read_manifest(&runtime_root.join("packaged_defaultspack_source_manifest.v1.json"))?;
    verify_and_snapshot_against_manifest_with_hook(runtime_root, snapshot_parent, &manifest, || {})
}

/// Verify against manifest bytes obtained from a separate trusted authority.
pub fn verify_and_snapshot_against_manifest(
    runtime_root: &Path,
    snapshot_parent: &Path,
    trusted_manifest: &[u8],
) -> io::Result<VerifiedSourceSnapshot> {
    verify_and_snapshot_against_manifest_with_hook(
        runtime_root,
        snapshot_parent,
        trusted_manifest,
        || {},
    )
}

fn verify_and_snapshot_against_manifest_with_hook(
    runtime_root: &Path,
    snapshot_parent: &Path,
    trusted_manifest: &[u8],
    before_copy: impl FnOnce(),
) -> io::Result<VerifiedSourceSnapshot> {
    let root_metadata = fs::symlink_metadata(runtime_root)?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err(invalid("packaged source root must be a real directory"));
    }
    if trusted_manifest.len() as u64 > MAX_MANIFEST_BYTES {
        return Err(invalid("trusted source manifest exceeds its size bound"));
    }
    let actual_manifest =
        read_manifest(&runtime_root.join("packaged_defaultspack_source_manifest.v1.json"))?;
    if actual_manifest != trusted_manifest {
        return Err(invalid(
            "working source manifest differs from the trusted authority",
        ));
    }
    let manifest = parse_manifest(trusted_manifest)?;
    let mut actual = BTreeSet::new();
    for relative in ROOTS {
        collect_actual(runtime_root, &runtime_root.join(relative), &mut actual)?;
    }
    for relative in FILES {
        let path = runtime_root.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(invalid(format!(
                "source closure file is not regular: {relative}"
            )));
        }
        reject_hardlink(&metadata, &path)?;
        actual.insert((*relative).to_owned());
    }
    if actual != manifest.keys().cloned().collect() {
        return Err(invalid(
            "actual source paths differ from the strict manifest",
        ));
    }
    before_copy();
    let snapshot_root = create_snapshot(snapshot_parent)?;
    let result = (|| {
        for (relative, expected) in &manifest {
            copy_verified(
                &runtime_root.join(relative),
                &snapshot_root.join(relative),
                expected,
            )?;
        }
        if identity(&fs::symlink_metadata(runtime_root)?) != identity(&root_metadata) {
            return Err(invalid("packaged source root changed during verification"));
        }
        Ok(VerifiedSourceSnapshot {
            root: snapshot_root.clone(),
        })
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&snapshot_root);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Tree(PathBuf);
    impl Tree {
        fn new(label: &str) -> Self {
            let root = std::env::temp_dir().join(format!(
                "tobkiri-source-{label}-{}-{}",
                std::process::id(),
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            fs::create_dir_all(&root).unwrap();
            Self(root)
        }
    }
    impl Drop for Tree {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn fixture(tree: &Tree) -> PathBuf {
        let root = tree.0.join("runtime");
        if root.exists() {
            fs::remove_dir_all(&root).unwrap();
        }
        for relative in ROOTS {
            fs::create_dir_all(root.join(relative)).unwrap();
        }
        let mut records = Vec::new();
        let mut paths = ROOTS
            .iter()
            .map(|root| format!("{root}/fixture.py"))
            .collect::<Vec<_>>();
        paths.extend(FILES.iter().map(|path| (*path).to_owned()));
        paths.sort();
        for relative in paths {
            let path = root.join(&relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            let payload = format!("safe:{relative}\n");
            fs::write(&path, payload.as_bytes()).unwrap();
            records.push(serde_json::json!({
                "path": relative, "type": "regular-file", "size": payload.len(),
                "sha256": format!("{:x}", Sha256::digest(payload.as_bytes())), "executable": false
            }));
        }
        fs::write(
            root.join("packaged_defaultspack_source_manifest.v1.json"),
            serde_json::to_vec(&serde_json::json!({
                "schema": SCHEMA, "roots": ROOTS, "files": records
            }))
            .unwrap(),
        )
        .unwrap();
        root
    }

    fn mutate_first_manifest_entry(root: &Path, mutate: impl FnOnce(&mut Value)) {
        let path = root.join("packaged_defaultspack_source_manifest.v1.json");
        let mut manifest: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        mutate(&mut manifest["files"][0]);
        fs::write(path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    }

    #[test]
    fn verified_snapshot_contains_only_manifest_bytes() {
        let tree = Tree::new("valid");
        let root = fixture(&tree);
        let snapshot = verify_and_snapshot(&root, &tree.0.join("snapshots")).unwrap();
        assert_eq!(
            fs::read(snapshot.root().join("scripts/fixture.py")).unwrap(),
            b"safe:scripts/fixture.py\n"
        );
        assert!(!snapshot
            .root()
            .join("packaged_defaultspack_source_manifest.v1.json")
            .exists());
    }

    #[test]
    fn repository_manifest_produces_a_verified_snapshot_without_python() {
        let tree = Tree::new("repository");
        let runtime_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .unwrap()
            .join("tobkiri_runtime");
        let snapshot = verify_and_snapshot(&runtime_root, &tree.0).unwrap();
        assert!(snapshot
            .root()
            .join("scripts/generate_packaged_defaultspack_v4_bundle.py")
            .is_file());
        assert!(!snapshot.root().join("scripts/__pycache__").exists());
    }

    #[test]
    fn tampered_source_fails_closed() {
        let tree = Tree::new("tamper");
        let root = fixture(&tree);
        fs::write(root.join("scripts/fixture.py"), b"tampered\n").unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[test]
    fn manifest_type_size_digest_and_executable_are_strict() {
        let tree = Tree::new("manifest-metadata");
        for field in ["type", "size", "sha256", "executable"] {
            let root = fixture(&tree);
            mutate_first_manifest_entry(&root, |entry| match field {
                "type" => entry["type"] = Value::String("device".to_owned()),
                "size" => entry["size"] = Value::from(1_000_000_u64),
                "sha256" => entry["sha256"] = Value::String("0".repeat(64)),
                "executable" => entry["executable"] = Value::Bool(true),
                _ => unreachable!(),
            });
            assert!(
                verify_and_snapshot(&root, &tree.0.join(format!("snapshot-{field}"))).is_err(),
                "manifest {field} drift must fail closed"
            );
        }
    }

    #[test]
    fn extra_pyc_fails_closed() {
        let tree = Tree::new("pyc");
        let root = fixture(&tree);
        fs::create_dir_all(root.join("scripts/__pycache__")).unwrap();
        fs::write(root.join("scripts/__pycache__/fixture.pyc"), b"code").unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn symlink_fails_closed() {
        let tree = Tree::new("symlink");
        let root = fixture(&tree);
        let source = root.join("scripts/fixture.py");
        fs::remove_file(&source).unwrap();
        std::os::unix::fs::symlink("../tobkiri_protocol/fixture.py", &source).unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn hardlink_fails_closed() {
        let tree = Tree::new("hardlink");
        let root = fixture(&tree);
        let source = root.join("scripts/fixture.py");
        let outside = tree.0.join("outside");
        fs::rename(&source, &outside).unwrap();
        fs::hard_link(&outside, &source).unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[test]
    fn unknown_manifest_marker_fails_before_source_can_execute() {
        let tree = Tree::new("marker");
        let root = fixture(&tree);
        fs::write(
            root.join("scripts/__init__.py"),
            b"raise SystemExit('EXECUTED')\n",
        )
        .unwrap();
        let manifest_path = root.join("packaged_defaultspack_source_manifest.v1.json");
        let mut manifest: Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        manifest["execute_verifier"] = Value::Bool(true);
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
        assert!(!tree.0.join("EXECUTED").exists());
    }

    #[test]
    fn working_manifest_must_match_trusted_git_authority() {
        let tree = Tree::new("manifest-authority");
        let root = fixture(&tree);
        let manifest_path = root.join("packaged_defaultspack_source_manifest.v1.json");
        let trusted = fs::read(&manifest_path).unwrap();
        let mut tampered: Value = serde_json::from_slice(&trusted).unwrap();
        tampered["files"][0]["sha256"] = Value::String("0".repeat(64));
        fs::write(manifest_path, serde_json::to_vec(&tampered).unwrap()).unwrap();
        let error =
            verify_and_snapshot_against_manifest(&root, &tree.0.join("snapshots"), &trusted)
                .unwrap_err();
        assert!(error.to_string().contains("trusted authority"));
    }

    #[test]
    fn file_swap_fails_closed() {
        let tree = Tree::new("file-swap");
        let root = fixture(&tree);
        let swapped = root.join("scripts/fixture.py");
        let manifest =
            read_manifest(&root.join("packaged_defaultspack_source_manifest.v1.json")).unwrap();
        let error = verify_and_snapshot_against_manifest_with_hook(
            &root,
            &tree.0.join("snapshots"),
            &manifest,
            || fs::write(&swapped, b"swapped\n").unwrap(),
        )
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn root_swap_fails_closed() {
        let tree = Tree::new("root-swap");
        let root = fixture(&tree);
        let moved = tree.0.join("moved-runtime");
        let replacement = tree.0.join("runtime");
        let manifest =
            read_manifest(&root.join("packaged_defaultspack_source_manifest.v1.json")).unwrap();
        let error = verify_and_snapshot_against_manifest_with_hook(
            &root,
            &tree.0.join("snapshots"),
            &manifest,
            || {
                fs::rename(&root, &moved).unwrap();
                fs::create_dir(&replacement).unwrap();
            },
        )
        .unwrap_err();
        assert!(error.to_string().contains("source") || error.kind() == io::ErrorKind::NotFound);
    }
}
