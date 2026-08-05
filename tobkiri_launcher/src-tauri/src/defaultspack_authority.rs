//! Pack v4 authority resolution for the Launcher-owned Defaultspack guardian.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Component, Path, PathBuf};

use anyhow::{bail, Context, Result};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::config::AppConfig;

const DEFAULT_PROFILE_ID: &str = "defaults";
const DEFAULT_BASE_ID: &str = "defaults-basepack";
const DEFAULT_SHELL_ID: &str = "shell.tauri.default";
const DEFAULT_RUNTIME_ID: &str = "runtime.tauri.application.default";
const DEFAULT_PROFILE_SOURCE: &str =
    "tobkiri_runtime/ecosystem/defaultspack/v4/defaults.profile.v4.json";
const BUNDLE_SCHEMA: &str = "io.tobkiri.defaultspack-bundle-lock.v1";
const PROFILE_PATH: &str = "defaults.profile.v4.json";
const DEFAULTSPACK_PACK_PATH: &str = "packs/defaultspack.pack.v4.json";
const BASE_PACK_PATH: &str = "packs/defaults-basepack.pack.v4.json";
const SHELL_PACK_PATH: &str = "packs/shell.tauri.default.pack.v4.json";
const RUNTIME_PACK_PATH: &str = "packs/runtime.tauri.application.default.pack.v4.json";

/// Exact, immutable authority captured for one guardian launch.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct GuardianAuthority {
    pub pack_root: PathBuf,
    pub profile_id: String,
    pub profile_digest: String,
    pub catalog_revision: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BundleLock {
    schema: String,
    entries: Vec<BundleEntry>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BundleEntry {
    path: String,
    kind: String,
    digest: String,
}

/// Resolve guardian launch metadata solely from packaged v4 authorities.
pub(crate) fn resolve(config: &AppConfig) -> Result<GuardianAuthority> {
    let catalog = crate::presentation::load_catalog(config)
        .context("Defaultspack guardian presentation authority was rejected")?;
    if catalog.default_profile_id != DEFAULT_PROFILE_ID
        || catalog.default_profile_source != DEFAULT_PROFILE_SOURCE
        || catalog.default_selection.base_pack_id != DEFAULT_BASE_ID
        || catalog.default_selection.shell_provider_id != DEFAULT_SHELL_ID
        || catalog.base_packs.len() != 1
        || catalog.shell_providers.len() != 1
    {
        bail!("Defaultspack guardian requires the exact Defaults Base and Tauri Shell Profile");
    }
    let base = &catalog.base_packs[0];
    if base.pack_id != DEFAULT_BASE_ID || base.backend_provider_ids != ["defaultspack"] {
        bail!("Defaults Base must bind exactly one Defaultspack backend provider");
    }
    let shell = &catalog.shell_providers[0];
    if shell.provider_id != DEFAULT_SHELL_ID
        || shell
            .artifact_variants
            .iter()
            .any(|variant| variant.development_command.is_some())
    {
        bail!("Defaultspack guardian Shell authority is not production-only");
    }

    let app_root = canonical_directory(&config.app_dir, "packaged application root")?;
    let pack_root = canonical_child_directory(
        &app_root,
        Path::new("ecosystem/defaultspack"),
        "Defaultspack Pack root",
    )?;
    let bundle_root = canonical_child_directory(&pack_root, Path::new("v4"), "Pack v4 root")?;
    let entries = verify_bundle_lock(&bundle_root)?;

    require_catalog_digest(
        &entries,
        BASE_PACK_PATH,
        catalog.source_manifest_digests.get(DEFAULT_BASE_ID),
    )?;
    require_catalog_digest(
        &entries,
        DEFAULTSPACK_PACK_PATH,
        catalog.source_manifest_digests.get("defaultspack"),
    )?;
    require_catalog_digest(
        &entries,
        SHELL_PACK_PATH,
        catalog.source_manifest_digests.get(DEFAULT_SHELL_ID),
    )?;
    require_catalog_digest(
        &entries,
        RUNTIME_PACK_PATH,
        catalog.source_manifest_digests.get(DEFAULT_RUNTIME_ID),
    )?;
    require_catalog_digest(
        &entries,
        PROFILE_PATH,
        Some(&catalog.default_profile_digest),
    )?;

    let profile = read_json(&bundle_root.join(PROFILE_PATH), "Defaults Profile v4")?;
    validate_profile(&profile)?;
    validate_defaultspack_pack(&read_json(
        &bundle_root.join(DEFAULTSPACK_PACK_PATH),
        "Defaultspack Pack v4",
    )?)?;
    verify_pack_artifact_index(&pack_root, &bundle_root)?;

    let desktop_entry = pack_root.join("defaultspack/desktop_app.py");
    read_regular_file(&desktop_entry, "Defaultspack desktop entrypoint")?;

    let catalog_revision = crate::presentation::catalog_revision(&catalog)?;
    Ok(GuardianAuthority {
        pack_root,
        profile_id: DEFAULT_PROFILE_ID.to_string(),
        profile_digest: catalog.default_profile_digest,
        catalog_revision,
    })
}

fn canonical_directory(path: &Path, label: &str) -> Result<PathBuf> {
    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("{label} is missing at {}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        bail!("{label} must be a non-symlink directory");
    }
    path.canonicalize()
        .with_context(|| format!("failed to canonicalize {label}"))
}

fn canonical_child_directory(root: &Path, relative: &Path, label: &str) -> Result<PathBuf> {
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        bail!("{label} has an unsafe path");
    }
    let child = canonical_directory(&root.join(relative), label)?;
    if !child.starts_with(root) {
        bail!("{label} escapes the packaged application root");
    }
    Ok(child)
}

fn read_regular_file(path: &Path, label: &str) -> Result<Vec<u8>> {
    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("{label} is missing at {}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        bail!("{label} must be a regular non-symlink file");
    }
    fs::read(path).with_context(|| format!("failed to read {label} at {}", path.display()))
}

fn read_json(path: &Path, label: &str) -> Result<Value> {
    serde_json::from_slice(&read_regular_file(path, label)?)
        .with_context(|| format!("{label} is malformed"))
}

fn sha256(bytes: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(bytes))
}

fn safe_relative(value: &str) -> Result<PathBuf> {
    let path = PathBuf::from(value);
    if value.is_empty()
        || value.contains('\\')
        || path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
        || path.to_string_lossy().replace('\\', "/") != value
    {
        bail!("Pack v4 lock contains an unsafe path: {value:?}");
    }
    Ok(path)
}

fn collect_bundle_files(root: &Path, current: &Path, files: &mut BTreeSet<String>) -> Result<()> {
    for entry in fs::read_dir(current)
        .with_context(|| format!("failed to enumerate Pack v4 root at {}", current.display()))?
    {
        let entry = entry?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            bail!("Pack v4 authority may not be a symlink: {}", path.display());
        }
        if metadata.is_dir() {
            collect_bundle_files(root, &path, files)?;
        } else if metadata.is_file()
            && path.file_name().and_then(|name| name.to_str()) != Some("bundle.lock.json")
        {
            files.insert(
                path.strip_prefix(root)?
                    .to_string_lossy()
                    .replace('\\', "/"),
            );
        }
    }
    Ok(())
}

fn verify_bundle_lock(root: &Path) -> Result<BTreeMap<String, String>> {
    let raw = read_regular_file(&root.join("bundle.lock.json"), "Pack v4 bundle lock")?;
    let lock: BundleLock =
        serde_json::from_slice(&raw).context("Pack v4 bundle lock is malformed")?;
    if lock.schema != BUNDLE_SCHEMA || lock.entries.is_empty() {
        bail!("Pack v4 bundle lock schema or entries are invalid");
    }
    let mut verified = BTreeMap::new();
    for entry in lock.entries {
        if !matches!(entry.kind.as_str(), "pack" | "base" | "shell" | "profile") {
            bail!("Pack v4 bundle lock contains an invalid authority kind");
        }
        let relative = safe_relative(&entry.path)?;
        let candidate = root.join(&relative);
        let bytes = read_regular_file(&candidate, "Pack v4 locked authority")?;
        if sha256(&bytes) != entry.digest {
            bail!("Pack v4 locked authority digest mismatch: {}", entry.path);
        }
        let canonical = candidate.canonicalize()?;
        if !canonical.starts_with(root) {
            bail!("Pack v4 locked authority escapes its root: {}", entry.path);
        }
        if verified.insert(entry.path.clone(), entry.digest).is_some() {
            bail!("Pack v4 bundle lock contains a duplicate path");
        }
    }
    let mut actual = BTreeSet::new();
    collect_bundle_files(root, root, &mut actual)?;
    if actual != verified.keys().cloned().collect() {
        bail!("Pack v4 bundle inventory differs from its lock");
    }
    Ok(verified)
}

fn require_catalog_digest(
    entries: &BTreeMap<String, String>,
    path: &str,
    catalog_digest: Option<&String>,
) -> Result<()> {
    let locked = entries
        .get(path)
        .with_context(|| format!("Pack v4 lock is missing {path}"))?;
    if catalog_digest.map(String::as_str) != Some(locked.as_str()) {
        bail!("Packaged catalog and Pack v4 lock disagree for {path}");
    }
    Ok(())
}

fn value_str<'a>(value: &'a Value, pointer: &str) -> Option<&'a str> {
    value.pointer(pointer).and_then(Value::as_str)
}

fn validate_profile(profile: &Value) -> Result<()> {
    if value_str(profile, "/profile_api_version") != Some("io.tobkiri.profile.v4")
        || value_str(profile, "/profile_id") != Some(DEFAULT_PROFILE_ID)
        || value_str(profile, "/mode") != Some("interactive")
        || value_str(profile, "/base/pack_id") != Some(DEFAULT_BASE_ID)
        || value_str(profile, "/shell/provider_id") != Some(DEFAULT_SHELL_ID)
        || value_str(profile, "/shell/pack_id") != Some(DEFAULT_SHELL_ID)
        || value_str(profile, "/shell/contract_id") != Some("app.shell.v1")
        || value_str(profile, "/shell/platform") != Some(current_platform())
        || value_str(profile, "/shell/architecture") != Some(current_architecture())
    {
        bail!("Defaults Profile does not bind the exact Base and Tauri Shell");
    }
    let packs = profile
        .get("packs")
        .and_then(Value::as_array)
        .context("Defaults Profile packs must be an array")?;
    let effective = packs
        .iter()
        .map(|item| {
            Ok((
                value_str(item, "/pack_id").context("Defaults Profile pack is missing pack_id")?,
                value_str(item, "/role").context("Defaults Profile pack is missing role")?,
            ))
        })
        .collect::<Result<BTreeSet<_>>>()?;
    let expected = BTreeSet::from([
        ("defaultspack", "provider"),
        ("rumi_file_inspect_pack", "provider"),
        (DEFAULT_RUNTIME_ID, "application"),
    ]);
    if packs.len() != expected.len()
        || effective != expected
        || effective
            .iter()
            .any(|(identity, _)| identity.starts_with("shell.cli.") || identity.starts_with("dev."))
    {
        bail!("Defaults Profile effective Pack set is not the finite production set");
    }
    Ok(())
}

fn validate_defaultspack_pack(pack: &Value) -> Result<()> {
    let providers = pack
        .get("provider_catalog")
        .and_then(Value::as_array)
        .context("Defaultspack provider catalog must be an array")?;
    if value_str(pack, "/pack_api_version") != Some("io.tobkiri.pack.v4")
        || value_str(pack, "/pack/id") != Some("defaultspack")
        || value_str(pack, "/migration/compatibility") != Some("none")
        || providers.len() != 1
        || value_str(&providers[0], "/provider_id") != Some("defaultspack.conversation")
    {
        bail!("Defaultspack Pack v4 must expose exactly one canonical provider");
    }
    Ok(())
}

fn verify_pack_artifact_index(pack_root: &Path, bundle_root: &Path) -> Result<()> {
    let index = read_json(
        &pack_root.join("artifact-index.v4.json"),
        "Defaultspack artifact index",
    )?;
    if value_str(&index, "/index_api_version") != Some("io.tobkiri.pack-artifact-index.v4")
        || value_str(&index, "/pack_id") != Some("defaultspack")
    {
        bail!("Defaultspack artifact index identity is invalid");
    }
    let signed_digest = value_str(&index, "/integrity_seal/signed_digest")
        .context("Defaultspack artifact index seal is missing")?;
    let mut unsigned_index = index.clone();
    unsigned_index
        .as_object_mut()
        .context("Defaultspack artifact index must be an object")?
        .remove("integrity_seal");
    if sha256(&serde_json::to_vec(&unsigned_index)?) != signed_digest {
        bail!("Defaultspack artifact index integrity seal is stale");
    }
    let entries = index
        .get("artifacts")
        .and_then(Value::as_array)
        .context("Defaultspack artifact index entries must be an array")?;
    let mut actual = BTreeMap::new();
    for entry in entries {
        let relative = value_str(entry, "/path").context("artifact index path is missing")?;
        let expected = value_str(entry, "/digest").context("artifact index digest is missing")?;
        let bytes = read_regular_file(&pack_root.join(safe_relative(relative)?), "Pack artifact")?;
        if sha256(&bytes) != expected || actual.insert(relative, expected).is_some() {
            bail!("Defaultspack artifact index contains a duplicate or stale artifact");
        }
    }
    for required in [
        "pack.v4.json",
        "contracts.v4.json",
        "runtime/conversation.py",
    ] {
        if !actual.contains_key(required) {
            bail!("Defaultspack artifact index is missing {required}");
        }
    }
    let root_pack = read_regular_file(&pack_root.join("pack.v4.json"), "Defaultspack Pack")?;
    let bundled_pack = read_regular_file(
        &bundle_root.join(DEFAULTSPACK_PACK_PATH),
        "locked Defaultspack Pack",
    )?;
    if root_pack != bundled_pack {
        bail!("Defaultspack root Pack differs from the locked Profile Pack");
    }
    let pack: Value =
        serde_json::from_slice(&root_pack).context("Defaultspack Pack v4 is malformed")?;
    let artifact_set_digest = value_str(&index, "/artifact_set_digest");
    if artifact_set_digest != value_str(&pack, "/integrity/artifact_set_digest")
        || artifact_set_digest != value_str(&pack, "/pack/artifact_digest")
        || value_str(&index, "/source_identity") != value_str(&pack, "/integrity/source_identity")
    {
        bail!("Defaultspack artifact index is stale for its Pack v4 authority");
    }
    Ok(())
}

fn current_platform() -> &'static str {
    if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else {
        "unsupported"
    }
}

fn current_architecture() -> &'static str {
    if cfg!(target_arch = "aarch64") {
        "arm64"
    } else if cfg!(target_arch = "x86_64") {
        "x86_64"
    } else {
        "unsupported"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn copy_tree(source: &Path, destination: &Path) {
        fs::create_dir_all(destination).unwrap();
        for entry in fs::read_dir(source).unwrap() {
            let entry = entry.unwrap();
            let source_path = entry.path();
            let destination_path = destination.join(entry.file_name());
            if entry.file_type().unwrap().is_dir() {
                copy_tree(&source_path, &destination_path);
            } else {
                fs::copy(source_path, destination_path).unwrap();
            }
        }
    }

    fn fixture(name: &str) -> (PathBuf, AppConfig) {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "tobkiri-defaultspack-authority-{name}-{}-{unique}",
            std::process::id()
        ));
        let app_dir = root
            .join("Relocated")
            .join("Tobkiri Launcher.app")
            .join("Contents/Resources/app");
        let repository = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let source_pack = repository.join("tobkiri_runtime/ecosystem/defaultspack");
        let destination_pack = app_dir.join("ecosystem/defaultspack");
        copy_tree(&source_pack.join("v4"), &destination_pack.join("v4"));
        for relative in [
            "pack.v4.json",
            "contracts.v4.json",
            "artifact-index.v4.json",
            "runtime/conversation.py",
            "defaultspack/desktop_app.py",
        ] {
            let source = source_pack.join(relative);
            let destination = destination_pack.join(relative);
            fs::create_dir_all(destination.parent().unwrap()).unwrap();
            fs::copy(source, destination).unwrap();
        }
        fs::create_dir_all(app_dir.join("bundled")).unwrap();
        fs::copy(
            repository.join("tobkiri_launcher/src-tauri/bundled/presentation_catalog.json"),
            app_dir.join("bundled/presentation_catalog.json"),
        )
        .unwrap();
        let config = AppConfig {
            app_dir: app_dir.clone(),
            rumi_home: app_dir,
            python_dir: root.join("Application Support/python"),
            uv_path: root.join("Application Support/uv"),
            venv_dir: root.join("Application Support/venv"),
            user_data_dir: root.join("Application Support/user_data"),
            log_dir: root.join("Application Support/logs"),
            kernel_port: 8765,
            dev_workspace_root: None,
        };
        (root, config)
    }

    #[test]
    fn relocated_packaged_first_start_and_restart_use_identical_v4_authority() {
        let (root, config) = fixture("relocated-restart");
        let retired = config.app_dir.join("ecosystem/defaultspack/ecosystem.json");
        assert!(
            !retired.exists(),
            "retired ecosystem.json must remain absent"
        );

        let first = resolve(&config).unwrap();
        let restarted = resolve(&config).unwrap();

        assert_eq!(first, restarted);
        assert_eq!(first.profile_id, DEFAULT_PROFILE_ID);
        assert_eq!(
            first.pack_root,
            config
                .app_dir
                .join("ecosystem/defaultspack")
                .canonicalize()
                .unwrap()
        );
        assert!(
            !retired.exists(),
            "guardian preparation must not synthesize legacy state"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_tampered_and_stale_v4_authority_fail_closed() {
        let (missing_root, missing_config) = fixture("missing");
        fs::remove_file(
            missing_config
                .app_dir
                .join("ecosystem/defaultspack/v4/defaults.profile.v4.json"),
        )
        .unwrap();
        assert!(resolve(&missing_config).is_err());
        fs::remove_dir_all(missing_root).unwrap();

        let (tampered_root, tampered_config) = fixture("tampered");
        fs::write(
            tampered_config
                .app_dir
                .join("ecosystem/defaultspack/v4/defaults.profile.v4.json"),
            b"{}",
        )
        .unwrap();
        assert!(resolve(&tampered_config).is_err());
        fs::remove_dir_all(tampered_root).unwrap();

        let (stale_root, stale_config) = fixture("stale");
        let catalog_path = stale_config
            .app_dir
            .join("bundled/presentation_catalog.json");
        let mut catalog: Value = serde_json::from_slice(&fs::read(&catalog_path).unwrap()).unwrap();
        catalog["default_profile_digest"] = Value::String(format!("sha256:{}", "0".repeat(64)));
        fs::write(catalog_path, serde_json::to_vec(&catalog).unwrap()).unwrap();
        assert!(resolve(&stale_config).is_err());
        fs::remove_dir_all(stale_root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn symlinked_and_escaping_v4_authority_fail_closed() {
        use std::os::unix::fs::symlink;

        let (symlink_root, symlink_config) = fixture("symlink");
        let profile = symlink_config
            .app_dir
            .join("ecosystem/defaultspack/v4/defaults.profile.v4.json");
        let outside = symlink_root.join("outside.profile.json");
        fs::rename(&profile, &outside).unwrap();
        symlink(&outside, &profile).unwrap();
        assert!(resolve(&symlink_config).is_err());
        fs::remove_dir_all(symlink_root).unwrap();

        let (escape_root, escape_config) = fixture("escape");
        let lock_path = escape_config
            .app_dir
            .join("ecosystem/defaultspack/v4/bundle.lock.json");
        let mut lock: Value = serde_json::from_slice(&fs::read(&lock_path).unwrap()).unwrap();
        lock["entries"][0]["path"] = Value::String("../outside.json".to_string());
        fs::write(lock_path, serde_json::to_vec(&lock).unwrap()).unwrap();
        assert!(resolve(&escape_config).is_err());
        fs::remove_dir_all(escape_root).unwrap();
    }
}
