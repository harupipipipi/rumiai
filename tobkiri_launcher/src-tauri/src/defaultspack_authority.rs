//! Pack v4 authority resolution for the Launcher-owned Defaultspack guardian.

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::fs;
use std::path::{Component, Path, PathBuf};

use anyhow::{bail, Context, Result};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

#[cfg(test)]
#[path = "packaging_toolchain.rs"]
mod packaging_toolchain;

use crate::config::AppConfig;

const DEFAULT_PROFILE_ID: &str = "defaults";
const DEFAULT_BASE_ID: &str = "defaults-basepack";
const DEFAULT_SHELL_ID: &str = "shell.tauri.default";
const DEFAULT_RUNTIME_ID: &str = "runtime.tauri.application.default";
const DEFAULT_PROFILE_API_VERSION: &str = "io.tobkiri.profile.v5";
const DEFAULT_PROFILE_SOURCE: &str =
    "tobkiri_runtime/ecosystem/defaultspack/v4/defaults.profile.v4.json";
const DEFAULT_PROVIDER_PACK_IDS: [&str; 13] = [
    "defaultspack",
    "rumi_ai_gateway_pack",
    "rumi_ai_pipeline_pack",
    "rumi_ai_routing_pack",
    "rumi_ai_stream_pack",
    "rumi_ai_tool_bridge_pack",
    "rumi_ai_usage_pack",
    "rumi_file_inspect_pack",
    "rumi_model_catalog_pack",
    "rumi_model_registry_pack",
    "rumi_provider_adapters_pack",
    "rumi_provider_registry_pack",
    "tobkiri_host_pack_control",
];
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
    pub launch: GuardianLaunch,
    pub profile_id: String,
    pub profile_digest: String,
    pub catalog_revision: String,
}

/// Verified process materialization for the application Pack's launch function.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct GuardianLaunch {
    pub entrypoint: PathBuf,
    pub argv: Vec<OsString>,
    pub artifact_digest: String,
    pub function_id: String,
    pub provider_id: String,
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
    verify_symlink_free_tree(&pack_root, &pack_root)?;
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
        PROFILE_PATH,
        Some(&catalog.default_profile_digest),
    )?;
    // Shell and Application are intentional packaged successors of the signed
    // source definitions. Their exact bytes are bound by the sealed bundle
    // lock; Profile is additionally bound to the catalog above, and the
    // selected release artifact is independently bound below.
    for path in [SHELL_PACK_PATH, RUNTIME_PACK_PATH, PROFILE_PATH] {
        if !entries.contains_key(path) {
            bail!("packaged authority is absent from the bundle lock: {path}");
        }
    }

    let profile = read_json(&bundle_root.join(PROFILE_PATH), "Defaults Profile v5")?;
    let selected_variant = validate_profile(&profile, &catalog)?;
    validate_defaultspack_pack(&read_json(
        &bundle_root.join(DEFAULTSPACK_PACK_PATH),
        "Defaultspack Pack v4",
    )?)?;
    let launch = validate_application_pack(
        &pack_root,
        &read_json(
            &bundle_root.join(RUNTIME_PACK_PATH),
            "Defaultspack application Pack v4",
        )?,
        selected_variant,
    )?;
    verify_pack_artifact_index(&pack_root, &bundle_root)?;

    let catalog_revision = crate::presentation::catalog_revision(&catalog)?;
    let profile_digest = entries
        .get(PROFILE_PATH)
        .context("packaged Profile is absent from the bundle lock")?
        .clone();
    Ok(GuardianAuthority {
        pack_root,
        launch,
        profile_id: DEFAULT_PROFILE_ID.to_string(),
        profile_digest,
        catalog_revision,
    })
}

fn validate_application_pack(
    pack_root: &Path,
    pack: &Value,
    selected_variant: &crate::presentation::ArtifactVariant,
) -> Result<GuardianLaunch> {
    let selected_platform = format!(
        "{}-{}",
        selected_variant.platform, selected_variant.architecture
    );
    let functions = pack
        .get("functions")
        .and_then(Value::as_array)
        .context("application Pack functions must be an array")?;
    let providers = pack
        .get("provider_catalog")
        .and_then(Value::as_array)
        .context("application Pack providers must be an array")?;
    let operations = pack
        .get("operation_catalog")
        .and_then(Value::as_array)
        .context("application Pack operations must be an array")?;
    let artifacts = pack
        .get("artifacts")
        .and_then(Value::as_array)
        .context("application Pack artifacts must be an array")?;
    if value_str(pack, "/pack_api_version") != Some("io.tobkiri.pack.v4")
        || value_str(pack, "/pack/id") != Some(DEFAULT_RUNTIME_ID)
        || value_str(pack, "/pack/kind") != Some("application")
        || value_str(pack, "/migration/compatibility") != Some("none")
        || functions.len() != 1
        || providers.len() != 1
        || operations.len() != 1
        || artifacts.len() != 2
        || value_str(&functions[0], "/id") != Some(DEFAULT_RUNTIME_ID)
        || value_str(&functions[0], "/isolation") != Some("dedicated_process")
        || functions[0]["operations"] != serde_json::json!(["launch"])
        || value_str(&providers[0], "/provider_id") != Some(DEFAULT_RUNTIME_ID)
        || value_str(&providers[0], "/owner") != Some(DEFAULT_RUNTIME_ID)
        || value_str(&providers[0], "/contract_reference") != Some("runtime.tauri.application.v1")
        || providers[0]["operations"] != serde_json::json!(["launch"])
        || value_str(&operations[0], "/operation_id") != Some("launch")
        || value_str(&operations[0], "/owner") != Some(DEFAULT_RUNTIME_ID)
        || value_str(&operations[0], "/provider_id") != Some(DEFAULT_RUNTIME_ID)
        || value_str(&operations[0], "/contract_reference") != Some("runtime.tauri.application.v1")
        || value_str(&artifacts[0], "/kind") != Some("executable")
        || value_str(&artifacts[0], "/platform") != Some(selected_platform.as_str())
        || value_str(&artifacts[1], "/path") != Some("defaultspack/frontend_contract_map.v4.json")
        || value_str(&artifacts[1], "/kind") != Some("asset")
        || value_str(&artifacts[1], "/platform") != Some("host")
        || artifacts[1].get("entrypoint").is_some()
        || artifacts[1].get("argv").is_some()
    {
        bail!("application Pack launch identity is invalid");
    }

    let artifact_digest = value_str(&artifacts[0], "/digest")
        .context("application Pack artifact digest is missing")?;
    let entrypoint_digest = value_str(&artifacts[0], "/entrypoint_digest")
        .context("application Pack entrypoint digest is missing")?;
    #[cfg(not(test))]
    if selected_variant.sha256.as_deref() != Some(artifact_digest)
        || selected_variant.entrypoint_sha256.as_deref() != Some(entrypoint_digest)
    {
        bail!("application Pack differs from its signed release artifact");
    }
    #[cfg(test)]
    if selected_variant
        .sha256
        .as_deref()
        .is_some_and(|digest| digest != artifact_digest)
        || selected_variant
            .entrypoint_sha256
            .as_deref()
            .is_some_and(|digest| digest != entrypoint_digest)
    {
        bail!("application Pack differs from its test release artifact");
    }
    if value_str(&functions[0], "/implementation_digest") != Some(entrypoint_digest)
        || value_str(pack, "/pack/artifact_digest")
            != value_str(pack, "/integrity/artifact_set_digest")
        || sha256(&serde_json::to_vec(artifacts)?)
            != value_str(pack, "/integrity/artifact_set_digest").unwrap_or_default()
    {
        bail!("application Pack artifact identity is inconsistent");
    }

    let artifact_path =
        value_str(&artifacts[0], "/path").context("application Pack artifact path is missing")?;
    let entrypoint = value_str(&artifacts[0], "/entrypoint")
        .context("application Pack entrypoint is missing")?;
    if artifact_path != selected_variant.artifact_ref || entrypoint != selected_variant.entrypoint {
        bail!("application Pack does not identify the selected Shell artifact");
    }
    let argv = artifacts[0]
        .get("argv")
        .and_then(Value::as_array)
        .context("application Pack argv must be an array")?;
    if !argv.is_empty() {
        bail!("application Pack launch argv must not contain positional arguments");
    }

    let artifact_relative = safe_relative(artifact_path)?;
    let relative = safe_relative(entrypoint)?;
    if !relative.starts_with(&artifact_relative) {
        bail!("application Pack entrypoint escapes its selected artifact");
    }
    let artifact_root = pack_root.join("platform-artifacts");
    let artifact_candidate = artifact_root.join(&artifact_relative);
    let candidate = artifact_root.join(relative);
    let bytes = read_regular_file(&candidate, "application Pack entrypoint")?;
    let canonical = candidate
        .canonicalize()
        .context("failed to canonicalize application Pack entrypoint")?;
    if !canonical.starts_with(&artifact_root)
        || artifact_tree_digest(&artifact_candidate)? != artifact_digest
        || sha256(&bytes) != entrypoint_digest
    {
        bail!("application Pack entrypoint escaped or failed artifact verification");
    }

    let contract_map_path = value_str(&artifacts[1], "/path")
        .context("application Pack frontend contract map path is missing")?;
    let contract_map_digest = value_str(&artifacts[1], "/digest")
        .context("application Pack frontend contract map digest is missing")?;
    let contract_map_candidate = pack_root.join(safe_relative(contract_map_path)?);
    let contract_map_bytes = read_regular_file(
        &contract_map_candidate,
        "application Pack frontend contract map",
    )?;
    let contract_map_canonical = contract_map_candidate
        .canonicalize()
        .context("failed to canonicalize application Pack frontend contract map")?;
    if !contract_map_canonical.starts_with(pack_root)
        || sha256(&contract_map_bytes) != contract_map_digest
    {
        bail!("application Pack frontend contract map escaped or failed artifact verification");
    }
    let contract_map: Value = serde_json::from_slice(&contract_map_bytes)
        .context("application Pack frontend contract map is malformed")?;
    if value_str(&contract_map, "/schema") != Some("io.tobkiri.frontend-contract-map.v4")
        || value_str(&contract_map, "/pack_id") != Some("defaultspack")
        || contract_map
            .get("routes")
            .and_then(Value::as_array)
            .is_none()
    {
        bail!("application Pack frontend contract map identity is invalid");
    }

    Ok(GuardianLaunch {
        entrypoint: canonical,
        argv: Vec::new(),
        artifact_digest: entrypoint_digest.to_string(),
        function_id: DEFAULT_RUNTIME_ID.to_string(),
        provider_id: DEFAULT_RUNTIME_ID.to_string(),
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

fn verify_symlink_free_tree(root: &Path, current: &Path) -> Result<()> {
    for entry in fs::read_dir(current)
        .with_context(|| format!("failed to inspect packaged tree at {}", current.display()))?
    {
        let entry = entry.context("failed to inspect packaged tree entry")?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).with_context(|| {
            format!(
                "failed to inspect packaged tree entry at {}",
                path.display()
            )
        })?;
        if metadata.file_type().is_symlink() {
            bail!(
                "packaged tree contains a symlink: {}",
                path.strip_prefix(root).unwrap_or(&path).display()
            );
        }
        if metadata.is_dir() {
            verify_symlink_free_tree(root, &path)?;
        } else if !metadata.is_file() {
            bail!(
                "packaged tree contains an unsupported entry: {}",
                path.strip_prefix(root).unwrap_or(&path).display()
            );
        } else if has_multiple_links(&path, &metadata)? {
            bail!(
                "packaged tree contains a multiply-linked file: {}",
                path.strip_prefix(root).unwrap_or(&path).display()
            );
        }
    }
    Ok(())
}

#[cfg(unix)]
fn has_multiple_links(_path: &Path, metadata: &fs::Metadata) -> Result<bool> {
    use std::os::unix::fs::MetadataExt;

    Ok(metadata.nlink() != 1)
}

#[cfg(windows)]
fn has_multiple_links(path: &Path, _metadata: &fs::Metadata) -> Result<bool> {
    use std::mem::MaybeUninit;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
    };

    let file = fs::File::open(path).with_context(|| {
        format!(
            "failed to inspect packaged file links at {}",
            path.display()
        )
    })?;
    let mut information = MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), information.as_mut_ptr()) } == 0 {
        return Err(std::io::Error::last_os_error()).with_context(|| {
            format!(
                "failed to inspect packaged file links at {}",
                path.display()
            )
        });
    }
    let information = unsafe { information.assume_init() };
    Ok(information.nNumberOfLinks != 1)
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

fn artifact_tree_digest(path: &Path) -> Result<String> {
    fn visit(root: &Path, path: &Path, hasher: &mut Sha256) -> Result<()> {
        let metadata = fs::symlink_metadata(path)
            .with_context(|| format!("packaged artifact is missing at {}", path.display()))?;
        if metadata.file_type().is_symlink() {
            bail!(
                "packaged artifact may not contain a symlink: {}",
                path.display()
            );
        }
        if metadata.is_file() {
            let relative = path
                .strip_prefix(root)
                .unwrap_or(Path::new(""))
                .to_string_lossy()
                .replace('\\', "/");
            hasher.update(relative.as_bytes());
            hasher.update([0]);
            hasher.update(read_regular_file(path, "packaged artifact file")?);
            return Ok(());
        }
        if !metadata.is_dir() {
            bail!(
                "packaged artifact contains an unsupported entry: {}",
                path.display()
            );
        }
        let mut children = fs::read_dir(path)?.collect::<std::io::Result<Vec<_>>>()?;
        children.sort_by_key(|entry| entry.file_name());
        for child in children {
            visit(root, &child.path(), hasher)?;
        }
        Ok(())
    }

    let mut hasher = Sha256::new();
    visit(path, path, &mut hasher)?;
    Ok(format!("sha256:{:x}", hasher.finalize()))
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

fn validate_profile<'a>(
    profile: &Value,
    catalog: &'a crate::presentation::PresentationCatalog,
) -> Result<&'a crate::presentation::ArtifactVariant> {
    let shell_platform = value_str(profile, "/shell/platform")
        .context("Defaults Profile Shell platform is missing")?;
    let shell_architecture = value_str(profile, "/shell/architecture")
        .context("Defaults Profile Shell architecture is missing")?;
    let declared_production_variant = catalog
        .shell_providers
        .iter()
        .find(|shell| shell.provider_id == DEFAULT_SHELL_ID)
        .and_then(|shell| {
            shell.artifact_variants.iter().find(|variant| {
                variant.platform == shell_platform
                    && variant.architecture == shell_architecture
                    && variant.production
                    && variant.prebuilt
                    && variant.development_command.is_none()
            })
        })
        .context("Defaults Profile has no exact packaged Shell variant")?;
    if value_str(profile, "/profile_api_version") != Some(DEFAULT_PROFILE_API_VERSION)
        || value_str(profile, "/profile_id") != Some(DEFAULT_PROFILE_ID)
        || value_str(profile, "/mode") != Some("interactive")
        || value_str(profile, "/state") != Some("needs_resolution")
        || value_str(profile, "/base/pack_id") != Some(DEFAULT_BASE_ID)
        || value_str(profile, "/shell/provider_id") != Some(DEFAULT_SHELL_ID)
        || value_str(profile, "/shell/pack_id") != Some(DEFAULT_SHELL_ID)
        || value_str(profile, "/shell/contract_id") != Some("app.shell.v1")
    {
        bail!("Defaults Profile does not bind the exact Base and Tauri Shell");
    }
    validate_effective_pack_set(profile)?;
    Ok(declared_production_variant)
}

fn validate_effective_pack_set(profile: &Value) -> Result<()> {
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
    let mut expected = DEFAULT_PROVIDER_PACK_IDS
        .iter()
        .map(|pack_id| (*pack_id, "provider"))
        .collect::<BTreeSet<_>>();
    expected.insert((DEFAULT_RUNTIME_ID, "application"));
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

#[cfg(test)]
mod tests {
    use super::packaging_toolchain;
    use super::*;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    const RELOCATION_LAYOUTS: &[(&str, &[&str])] = &[
        (
            "macos-bundle",
            &[
                "Relocated",
                "Tobkiri Launcher.app",
                "Contents",
                "Resources",
                "app",
            ],
        ),
        ("linux-prefix", &["opt", "tobkiri", "resources", "app"]),
        (
            "windows-install",
            &["Program Files", "Tobkiri Launcher", "resources", "app"],
        ),
    ];
    const SOURCE_MANIFEST_RELATIVE: &str =
        "tobkiri_runtime/packaged_defaultspack_source_manifest.v1.json";
    const SOURCE_MANIFEST_SCHEMA: &str = "io.tobkiri.packaged-defaultspack-source.v1";
    const ISOLATED_MODULE_CODE: &str = "import runpy,sys;source_root=sys.argv[1];module_name=sys.argv[2];sys.path.insert(0,source_root);sys.argv=[module_name,*sys.argv[3:]];runpy.run_module(module_name,run_name='__main__',alter_sys=True)";
    const ISOLATED_ENVIRONMENT_KEYS: &[&str] = &[
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "SystemRoot",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    ];

    fn verified_git() -> PathBuf {
        packaging_toolchain::verified_tool_executable("git")
            .expect("formal packaging Git binding should be available")
    }

    fn verified_python() -> PathBuf {
        packaging_toolchain::verified_tool_executable("python")
            .expect("formal packaging Python binding should be available")
    }

    fn rewrite_locked_document(
        config: &AppConfig,
        relative: &str,
        mutate: impl FnOnce(&mut Value),
    ) {
        let bundle = config.app_dir.join("ecosystem/defaultspack/v4");
        let path = bundle.join(relative);
        let mut document: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        mutate(&mut document);
        let raw = serde_json::to_vec(&document).unwrap();
        fs::write(&path, &raw).unwrap();

        let lock_path = bundle.join("bundle.lock.json");
        let mut lock: Value = serde_json::from_slice(&fs::read(&lock_path).unwrap()).unwrap();
        let entry = lock["entries"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|entry| entry["path"] == relative)
            .unwrap();
        entry["digest"] = Value::String(sha256(&raw));
        fs::write(lock_path, serde_json::to_vec(&lock).unwrap()).unwrap();

        let catalog_path = config.app_dir.join("bundled/presentation_catalog.json");
        let mut catalog: Value = serde_json::from_slice(&fs::read(&catalog_path).unwrap()).unwrap();
        if relative == RUNTIME_PACK_PATH {
            catalog["source_manifest_digests"][DEFAULT_RUNTIME_ID] = Value::String(sha256(&raw));
        } else if relative == PROFILE_PATH {
            catalog["default_profile_digest"] = Value::String(sha256(&raw));
        }
        fs::write(catalog_path, serde_json::to_vec(&catalog).unwrap()).unwrap();
    }

    fn rewrite_runtime_pack(config: &AppConfig, mutate: impl FnOnce(&mut Value)) {
        rewrite_locked_document(config, RUNTIME_PACK_PATH, mutate);
    }

    fn source_manifest_entries(source_checkout: &Path) -> BTreeMap<String, Value> {
        let manifest_path = source_checkout.join(SOURCE_MANIFEST_RELATIVE);
        let manifest = read_json(&manifest_path, "packaged Defaults source manifest").unwrap();
        let object = manifest
            .as_object()
            .expect("source manifest must be an object");
        let actual_fields = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
        let expected_fields = ["schema", "roots", "files"]
            .into_iter()
            .collect::<BTreeSet<_>>();
        assert_eq!(
            actual_fields, expected_fields,
            "source manifest fields drifted"
        );
        assert_eq!(
            object.get("schema").and_then(Value::as_str),
            Some(SOURCE_MANIFEST_SCHEMA),
            "source manifest schema drifted"
        );
        assert_eq!(
            object.get("roots"),
            Some(&serde_json::json!([
                "scripts",
                "tobkiri_protocol",
                "ecosystem/defaultspack/domain/runtime_v4",
                "ecosystem/defaultspack/v4",
                "ecosystem/defaultspack/runtime",
                "ecosystem/defaultspack/defaultspack",
            ])),
            "source manifest roots drifted"
        );
        let files = object
            .get("files")
            .and_then(Value::as_array)
            .expect("source manifest files must be an array");
        let mut entries = BTreeMap::new();
        let mut previous: Option<&str> = None;
        for entry in files {
            let entry_object = entry
                .as_object()
                .expect("source manifest entry must be an object");
            let fields = entry_object
                .keys()
                .map(String::as_str)
                .collect::<BTreeSet<_>>();
            let expected = ["path", "type", "size", "sha256", "executable"]
                .into_iter()
                .collect::<BTreeSet<_>>();
            assert_eq!(fields, expected, "source manifest file fields drifted");
            let relative = entry_object
                .get("path")
                .and_then(Value::as_str)
                .expect("source manifest path must be a string");
            if let Some(value) = previous {
                assert!(value < relative, "source manifest paths must be sorted");
            }
            previous = Some(relative);
            assert!(
                !relative.is_empty()
                    && !relative.contains('\\')
                    && !Path::new(relative).is_absolute()
                    && Path::new(relative)
                        .components()
                        .all(|component| matches!(component, Component::Normal(_))),
                "source manifest path is unsafe: {relative}"
            );
            assert_eq!(
                entry_object.get("type").and_then(Value::as_str),
                Some("regular-file"),
                "source manifest entry type drifted: {relative}"
            );
            let digest = entry_object
                .get("sha256")
                .and_then(Value::as_str)
                .expect("source manifest digest must be a string");
            assert!(
                digest.len() == 64
                    && digest.bytes().all(|character| character.is_ascii_hexdigit()
                        && !character.is_ascii_uppercase()),
                "source manifest digest must be lowercase raw SHA-256: {relative}"
            );
            assert!(
                entries.insert(relative.to_owned(), entry.clone()).is_none(),
                "source manifest contains duplicate path: {relative}"
            );
        }
        assert!(!entries.is_empty(), "source manifest must contain files");
        entries
    }

    fn source_file_digest(path: &Path) -> String {
        format!(
            "{:x}",
            Sha256::digest(&fs::read(path).expect("source file should be readable"))
        )
    }

    #[cfg(unix)]
    fn source_file_executable(metadata: &fs::Metadata) -> bool {
        use std::os::unix::fs::PermissionsExt;

        metadata.permissions().mode() & 0o111 != 0
    }

    #[cfg(not(unix))]
    fn source_file_executable(_metadata: &fs::Metadata) -> bool {
        false
    }

    fn collect_source_files(root: &Path, current: &Path, actual: &mut BTreeMap<String, Value>) {
        let entries = fs::read_dir(current).expect("source closure directory should be readable");
        for entry in entries {
            let entry = entry.expect("source closure entry should be readable");
            let path = entry.path();
            let metadata =
                fs::symlink_metadata(&path).expect("source closure metadata should exist");
            assert!(
                !metadata.file_type().is_symlink(),
                "source closure contains a symlink: {}",
                path.display()
            );
            if metadata.is_dir() {
                collect_source_files(root, &path, actual);
            } else {
                assert!(
                    metadata.is_file(),
                    "source closure contains a special entry: {}",
                    path.display()
                );
                assert!(
                    !has_multiple_links(&path, &metadata)
                        .expect("source links should be inspectable"),
                    "source closure contains a hardlink: {}",
                    path.display()
                );
                let relative = path
                    .strip_prefix(root)
                    .expect("source file should remain under closure root")
                    .to_string_lossy()
                    .replace('\\', "/");
                let record = serde_json::json!({
                    "path": relative,
                    "type": "regular-file",
                    "size": metadata.len(),
                    "sha256": source_file_digest(&path),
                    "executable": source_file_executable(&metadata),
                });
                assert!(
                    actual.insert(relative, record).is_none(),
                    "duplicate source path"
                );
            }
        }
    }

    fn assert_source_manifest_exact(source_checkout: &Path) {
        let expected = source_manifest_entries(source_checkout);
        let runtime_root = source_checkout.join("tobkiri_runtime");
        let manifest = runtime_root.join("packaged_defaultspack_source_manifest.v1.json");
        let mut actual = BTreeMap::new();
        let roots = [
            "scripts",
            "tobkiri_protocol",
            "ecosystem/defaultspack/domain/runtime_v4",
            "ecosystem/defaultspack/v4",
            "ecosystem/defaultspack/runtime",
            "ecosystem/defaultspack/defaultspack",
        ];
        for root in roots {
            collect_source_files(&runtime_root, &runtime_root.join(root), &mut actual);
        }
        for relative in [
            "ecosystem/defaultspack/pack.v4.json",
            "ecosystem/defaultspack/contracts.v4.json",
            "ecosystem/defaultspack/artifact-index.v4.json",
        ] {
            let path = runtime_root.join(relative);
            let metadata = fs::symlink_metadata(&path).expect("source file should exist");
            assert!(!metadata.file_type().is_symlink() && metadata.is_file());
            assert!(!has_multiple_links(&path, &metadata).unwrap());
            actual.insert(
                relative.to_owned(),
                serde_json::json!({
                    "path": relative,
                    "type": "regular-file",
                    "size": metadata.len(),
                    "sha256": source_file_digest(&path),
                    "executable": source_file_executable(&metadata),
                }),
            );
        }
        assert!(!actual.contains_key("packaged_defaultspack_source_manifest.v1.json"));
        assert_eq!(
            actual, expected,
            "source closure differs from shared manifest"
        );
        assert!(
            !manifest.is_symlink(),
            "source manifest itself may not be a symlink"
        );
    }

    fn clone_authoritative_fixture_source(repository: &Path, destination: &Path) -> String {
        let status = Command::new(verified_git())
            .args(["clone", "--quiet", "--shared", "--no-checkout", "--no-tags"])
            .arg(repository)
            .arg(destination)
            .status()
            .expect("authoritative fixture source clone should run");
        assert!(
            status.success(),
            "authoritative fixture source clone failed"
        );
        let manifest = source_manifest_entries(repository);
        let mut sparse_paths = vec!["sparse-checkout".to_owned(), "set".to_owned()];
        for relative in manifest.keys() {
            sparse_paths.push(format!("tobkiri_runtime/{relative}"));
        }
        sparse_paths.push(SOURCE_MANIFEST_RELATIVE.to_owned());
        sparse_paths.push("tobkiri_launcher/src-tauri/bundled".to_owned());
        let status = Command::new(verified_git())
            .args(&sparse_paths)
            .current_dir(destination)
            .status()
            .expect("authoritative fixture sparse checkout should run");
        assert!(
            status.success(),
            "authoritative fixture sparse checkout failed"
        );
        let status = Command::new(verified_git())
            .args(["checkout", "--quiet", "HEAD"])
            .current_dir(destination)
            .status()
            .expect("authoritative fixture checkout should run");
        assert!(status.success(), "authoritative fixture checkout failed");
        let revision = Command::new(verified_git())
            .args(["rev-parse", "--verify", "HEAD^{commit}"])
            .current_dir(destination)
            .output()
            .expect("authoritative fixture revision should be readable");
        assert!(
            revision.status.success(),
            "authoritative fixture revision lookup failed"
        );
        let revision = String::from_utf8(revision.stdout)
            .expect("authoritative fixture revision should be UTF-8")
            .trim()
            .to_owned();
        assert!(
            revision.len() == 40
                && revision
                    .bytes()
                    .all(|character| character.is_ascii_hexdigit()
                        && !character.is_ascii_uppercase()),
            "authoritative fixture revision must be a full lowercase SHA"
        );
        assert_clean_fixture_source(destination);
        revision
    }

    fn assert_clean_fixture_source(source_checkout: &Path) {
        let status = Command::new(verified_git())
            .args(["status", "--porcelain=v1", "--untracked-files=all"])
            .current_dir(source_checkout)
            .output()
            .expect("authoritative fixture status should be readable");
        assert!(
            status.status.success(),
            "authoritative fixture status failed"
        );
        assert!(
            status.stdout.is_empty(),
            "authoritative fixture source must remain clean"
        );
        assert!(
            !source_checkout
                .join(".github/scripts/packaging_cleanup.py")
                .exists(),
            "relocated generator must not retain the repository helper fallback"
        );
        assert_source_manifest_exact(source_checkout);
    }

    fn package_fixture_application(
        config: &AppConfig,
        source_checkout: &Path,
        source_revision: &str,
    ) {
        let source = config.app_dir.join("fixture-release/Tobkiri.app");
        let executable = source.join("Contents/MacOS/tobkiri-shell");
        fs::create_dir_all(executable.parent().unwrap()).unwrap();
        fs::write(
            &executable,
            b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01packaged Tauri fixture",
        )
        .unwrap();
        fs::write(
            source.join("Contents/Info.plist"),
            br#"<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict><key>CFBundleIdentifier</key>
<string>io.tobkiri.shell.tauri</string></dict></plist>"#,
        )
        .unwrap();
        fs::create_dir_all(source.join("Contents/Resources")).unwrap();
        fs::write(
            source.join("Contents/Resources/presentation.json"),
            b"sealed presentation fixture",
        )
        .unwrap();

        let python = verified_python();
        let hostile = config.app_dir.join("hostile-generator-input");
        fs::create_dir_all(hostile.join("scripts")).unwrap();
        let marker = hostile.join("executed.marker");
        let marker_literal = format!("{:?}", marker.to_string_lossy());
        fs::write(
            hostile.join("sitecustomize.py"),
            format!(
                "from pathlib import Path; Path({marker_literal}).write_text('sitecustomize')\n"
            ),
        )
        .unwrap();
        fs::write(
            hostile.join("usercustomize.py"),
            format!(
                "from pathlib import Path; Path({marker_literal}).write_text('usercustomize')\n"
            ),
        )
        .unwrap();
        fs::write(hostile.join("scripts/__init__.py"), "\n").unwrap();
        fs::write(
            hostile.join("scripts/generate_packaged_defaultspack_v4_bundle.py"),
            format!("from pathlib import Path; Path({marker_literal}).write_text('fake-module')\n"),
        )
        .unwrap();
        let unsafe_status = Command::new(&python)
            .args([
                "-B",
                "-m",
                "scripts.generate_packaged_defaultspack_v4_bundle",
                "--help",
            ])
            .env("PYTHONPATH", &hostile)
            .current_dir(&hostile)
            .status()
            .unwrap();
        assert!(unsafe_status.success());
        assert!(
            marker.exists(),
            "unsafe fixture launch should execute its marker"
        );
        fs::remove_file(&marker).unwrap();

        let source_root = source_checkout
            .join("tobkiri_runtime")
            .canonicalize()
            .unwrap();
        let mut isolated = Command::new(&python);
        isolated
            .env_clear()
            .args(["-I", "-B", "-c", ISOLATED_MODULE_CODE])
            .arg(&source_root)
            .arg("scripts.generate_packaged_defaultspack_v4_bundle")
            .arg("--source-artifact")
            .arg(&source)
            .arg("--bundle-root")
            .arg(config.app_dir.join("ecosystem/defaultspack/v4"))
            .arg("--artifact-root")
            .arg(
                config
                    .app_dir
                    .join("ecosystem/defaultspack/platform-artifacts"),
            )
            .arg("--relative-path")
            .arg("Tobkiri.app")
            .arg("--entrypoint")
            .arg("Tobkiri.app/Contents/MacOS/tobkiri-shell")
            .arg("--platform")
            .arg("macos")
            .arg("--architecture")
            .arg("arm64")
            .arg("--bundle-identity")
            .arg("io.tobkiri.shell.tauri")
            .arg("--source-commit")
            .arg(source_revision)
            .env(
                "GIT_CONFIG_GLOBAL",
                if cfg!(windows) { "NUL" } else { "/dev/null" },
            )
            .env("GIT_CONFIG_NOSYSTEM", "1");
        for key in ISOLATED_ENVIRONMENT_KEYS {
            if let Some(value) = std::env::var_os(key) {
                isolated.env(key, value);
            }
        }
        let status = isolated.current_dir(&hostile).status().unwrap();
        assert!(
            status.success(),
            "official packaged Profile generator failed"
        );
        assert!(
            !marker.exists(),
            "isolated fixture launch executed hostile input"
        );
        assert_clean_fixture_source(source_checkout);
        let bundle_root = config.app_dir.join("ecosystem/defaultspack/v4");
        let profile_raw = fs::read(bundle_root.join(PROFILE_PATH)).unwrap();
        let mut catalog: Value = serde_json::from_slice(
            &fs::read(config.app_dir.join("bundled/presentation_catalog.json")).unwrap(),
        )
        .unwrap();
        catalog["default_profile_digest"] = Value::String(sha256(&profile_raw));
        fs::write(
            config.app_dir.join("bundled/presentation_catalog.json"),
            serde_json::to_vec(&catalog).unwrap(),
        )
        .unwrap();
        for relative in [
            PROFILE_PATH,
            "shell.tauri.default.shell.v1.json",
            SHELL_PACK_PATH,
            RUNTIME_PACK_PATH,
        ] {
            let document: Value =
                serde_json::from_slice(&fs::read(bundle_root.join(relative)).unwrap()).unwrap();
            assert_eq!(
                value_str(&document, "/provenance/repository_commit"),
                Some(source_revision),
                "packaged fixture must retain its isolated release provenance"
            );
        }
    }

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

    fn fixture_at_layout(name: &str, layout: &[&str]) -> (PathBuf, AppConfig) {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "tobkiri-defaultspack-authority-{name}-{}-{unique}",
            std::process::id()
        ));
        let repository = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let source_checkout = root.join("authoritative-source");
        let source_revision = clone_authoritative_fixture_source(&repository, &source_checkout);
        let source_checkout = source_checkout
            .canonicalize()
            .expect("authoritative fixture source should be canonical");
        let app_dir = layout
            .iter()
            .fold(root.clone(), |path, component| path.join(component));
        let source_pack = source_checkout.join("tobkiri_runtime/ecosystem/defaultspack");
        let destination_pack = app_dir.join("ecosystem/defaultspack");
        copy_tree(&source_pack.join("v4"), &destination_pack.join("v4"));
        for relative in [
            "pack.v4.json",
            "contracts.v4.json",
            "artifact-index.v4.json",
            "runtime/conversation.py",
            "defaultspack/desktop_app.py",
            "defaultspack/frontend_contract_map.v4.json",
        ] {
            let source = source_pack.join(relative);
            let destination = destination_pack.join(relative);
            fs::create_dir_all(destination.parent().unwrap()).unwrap();
            fs::copy(source, destination).unwrap();
        }
        fs::create_dir_all(app_dir.join("bundled")).unwrap();
        fs::copy(
            source_checkout.join("tobkiri_launcher/src-tauri/bundled/presentation_catalog.json"),
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
        package_fixture_application(&config, &source_checkout, &source_revision);
        (root, config)
    }

    fn fixture(name: &str) -> (PathBuf, AppConfig) {
        fixture_at_layout(name, RELOCATION_LAYOUTS[0].1)
    }

    #[test]
    fn finite_production_pack_set_tracks_canonical_defaults_profile() {
        const AI_PACK_IDS: [&str; 10] = [
            "rumi_ai_gateway_pack",
            "rumi_ai_pipeline_pack",
            "rumi_ai_routing_pack",
            "rumi_ai_stream_pack",
            "rumi_ai_tool_bridge_pack",
            "rumi_ai_usage_pack",
            "rumi_model_catalog_pack",
            "rumi_model_registry_pack",
            "rumi_provider_adapters_pack",
            "rumi_provider_registry_pack",
        ];

        let repository = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let profile_path = repository.join(DEFAULT_PROFILE_SOURCE);
        let profile: Value = serde_json::from_slice(&fs::read(profile_path).unwrap()).unwrap();

        assert_eq!(value_str(&profile, "/base/pack_id"), Some(DEFAULT_BASE_ID));
        assert_eq!(
            value_str(&profile, "/profile_api_version"),
            Some(DEFAULT_PROFILE_API_VERSION)
        );
        assert_eq!(
            value_str(&profile, "/shell/pack_id"),
            Some(DEFAULT_SHELL_ID)
        );
        validate_effective_pack_set(&profile).unwrap();

        for pack_id in AI_PACK_IDS {
            let mut missing = profile.clone();
            missing["packs"]
                .as_array_mut()
                .unwrap()
                .retain(|pack| value_str(pack, "/pack_id") != Some(pack_id));
            assert!(
                validate_effective_pack_set(&missing).is_err(),
                "missing required AI Pack was accepted: {pack_id}"
            );
        }

        let mut extra = profile;
        extra["packs"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "pack_id": "unreviewed.extra.pack",
                "role": "provider"
            }));
        assert!(validate_effective_pack_set(&extra).is_err());
    }

    #[test]
    fn relocated_packaged_first_start_and_restart_use_identical_v4_authority() {
        for (layout_name, layout) in RELOCATION_LAYOUTS {
            let (root, config) =
                fixture_at_layout(&format!("relocated-restart-{layout_name}"), layout);
            let retired = config.app_dir.join("ecosystem/defaultspack/ecosystem.json");
            assert!(
                !retired.exists(),
                "retired ecosystem.json must remain absent for {layout_name}"
            );

            let first = resolve(&config).unwrap();
            let restarted = resolve(&config).unwrap();

            assert_eq!(first, restarted);
            assert_eq!(first.profile_id, DEFAULT_PROFILE_ID);
            assert!(first.launch.argv.is_empty());
            assert_eq!(first.launch.function_id, DEFAULT_RUNTIME_ID);
            assert_eq!(first.launch.provider_id, DEFAULT_RUNTIME_ID);
            assert_eq!(first.launch.entrypoint, restarted.launch.entrypoint);
            assert_eq!(
                first.launch.entrypoint,
                first
                    .pack_root
                    .join("platform-artifacts/Tobkiri.app/Contents/MacOS/tobkiri-shell",)
                    .canonicalize()
                    .unwrap()
            );
            assert_eq!(
                first.launch.artifact_digest,
                sha256(&fs::read(&first.launch.entrypoint).unwrap())
            );
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
                "guardian preparation must not synthesize legacy state for {layout_name}"
            );
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn relocated_entrypoint_tamper_fails_closed_across_packaged_layouts() {
        for (layout_name, layout) in RELOCATION_LAYOUTS {
            let (root, config) =
                fixture_at_layout(&format!("relocated-tamper-{layout_name}"), layout);
            resolve(&config).unwrap();

            fs::write(
                config
                    .app_dir
                    .join("ecosystem/defaultspack/platform-artifacts/Tobkiri.app/Contents/MacOS/tobkiri-shell"),
                b"raise SystemExit(0)\n",
            )
            .unwrap();

            let error = resolve(&config).unwrap_err().to_string();
            assert!(
                error.contains(
                    "application Pack entrypoint escaped or failed artifact verification"
                ),
                "unexpected tamper error for {layout_name}: {error}"
            );
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn macos_non_entrypoint_bundle_tamper_fails_tree_digest() {
        let (root, config) = fixture("macos-resource-tamper");
        resolve(&config).unwrap();
        fs::write(
            config.app_dir.join(
                "ecosystem/defaultspack/platform-artifacts/Tobkiri.app/Contents/Resources/presentation.json",
            ),
            b"tampered presentation fixture",
        )
        .unwrap();
        let error = resolve(&config).unwrap_err().to_string();
        assert!(
            error.contains("failed artifact verification"),
            "unexpected tree tamper error: {error}"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn duplicate_module_extra_and_wrong_launch_identities_fail_closed() {
        let mutations: &[fn(&mut Value)] = &[
            |pack| {
                pack["artifacts"][0]["argv"] = serde_json::json!(["defaultspack/desktop_app.py"]);
            },
            |pack| {
                pack["artifacts"][0]["argv"] =
                    serde_json::json!(["-m", "ecosystem.defaultspack.desktop_app"]);
            },
            |pack| pack["artifacts"][0]["argv"] = serde_json::json!(["unexpected"]),
            |pack| {
                pack["artifacts"][0]["entrypoint"] =
                    Value::String("runtime/conversation.py".into());
            },
            |pack| {
                pack["artifacts"][0]["digest"] =
                    Value::String(format!("sha256:{}", "0".repeat(64)));
            },
            |pack| pack["functions"][0]["id"] = Value::String("wrong.function".into()),
            |pack| {
                pack["provider_catalog"][0]["provider_id"] = Value::String("wrong.provider".into());
            },
        ];
        for (index, mutation) in mutations.iter().enumerate() {
            let (root, config) = fixture(&format!("invalid-launch-{index}"));
            rewrite_runtime_pack(&config, *mutation);
            assert!(resolve(&config).is_err(), "mutation {index} was accepted");
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn wrong_profile_path_escape_and_artifact_tamper_fail_closed() {
        let (profile_root, profile_config) = fixture("wrong-profile");
        rewrite_locked_document(&profile_config, PROFILE_PATH, |profile| {
            profile["profile_id"] = Value::String("wrong-profile".into());
        });
        assert!(resolve(&profile_config).is_err());
        fs::remove_dir_all(profile_root).unwrap();

        let (escape_root, escape_config) = fixture("entrypoint-escape");
        rewrite_runtime_pack(&escape_config, |pack| {
            pack["artifacts"][0]["path"] = Value::String("../desktop_app.py".into());
            pack["artifacts"][0]["entrypoint"] = Value::String("../desktop_app.py".into());
        });
        assert!(resolve(&escape_config).is_err());
        fs::remove_dir_all(escape_root).unwrap();

        let (tamper_root, tamper_config) = fixture("entrypoint-tamper");
        fs::write(
            tamper_config
                .app_dir
                .join("ecosystem/defaultspack/platform-artifacts/Tobkiri.app/Contents/MacOS/tobkiri-shell"),
            b"raise SystemExit(0)\n",
        )
        .unwrap();
        assert!(resolve(&tamper_config).is_err());
        fs::remove_dir_all(tamper_root).unwrap();

        let (contract_map_root, contract_map_config) = fixture("frontend-contract-map-tamper");
        fs::write(
            contract_map_config
                .app_dir
                .join("ecosystem/defaultspack/defaultspack/frontend_contract_map.v4.json"),
            b"{}",
        )
        .unwrap();
        assert!(resolve(&contract_map_config).is_err());
        fs::remove_dir_all(contract_map_root).unwrap();
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

        let (artifact_root, artifact_config) = fixture("artifact-symlink");
        let entrypoint = artifact_config
            .app_dir
            .join("ecosystem/defaultspack/defaultspack/desktop_app.py");
        let outside_entrypoint = artifact_root.join("outside.py");
        fs::rename(&entrypoint, &outside_entrypoint).unwrap();
        symlink(&outside_entrypoint, &entrypoint).unwrap();
        assert!(resolve(&artifact_config).is_err());
        fs::remove_dir_all(artifact_root).unwrap();

        let (contract_map_root, contract_map_config) = fixture("frontend-contract-map-symlink");
        let contract_map = contract_map_config
            .app_dir
            .join("ecosystem/defaultspack/defaultspack/frontend_contract_map.v4.json");
        let outside_contract_map = contract_map_root.join("outside.frontend-contract-map.json");
        fs::rename(&contract_map, &outside_contract_map).unwrap();
        symlink(&outside_contract_map, &contract_map).unwrap();
        assert!(resolve(&contract_map_config).is_err());
        fs::remove_dir_all(contract_map_root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn unindexed_external_hardlink_in_pack_tree_fails_closed() {
        let (root, config) = fixture("external-hardlink");
        let outside = root.join("outside-runtime.py");
        fs::write(&outside, b"raise SystemExit('outside mutation')\n").unwrap();
        fs::hard_link(
            &outside,
            config
                .app_dir
                .join("ecosystem/defaultspack/unindexed-runtime.py"),
        )
        .unwrap();

        let error = resolve(&config).unwrap_err().to_string();
        assert!(
            error.contains("multiply-linked file"),
            "unexpected hardlink error: {error}"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn ntfs_hardlink_count_is_detected() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "tobkiri-defaultspack-ntfs-hardlink-{}-{unique}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        let source = root.join("source.py");
        let linked = root.join("linked.py");
        fs::write(&source, b"pass\n").unwrap();
        fs::hard_link(&source, &linked).unwrap();

        let metadata = fs::symlink_metadata(&linked).unwrap();
        assert!(has_multiple_links(&linked, &metadata).unwrap());
        fs::remove_dir_all(root).unwrap();
    }
}
