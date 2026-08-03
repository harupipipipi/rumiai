//! Launcher-owned Base Pack/Shell selection and production launch boundary.
//!
//! The catalog is metadata only. Selecting a Base Pack or Shell never creates a
//! Grant and never executes Pack code. A launch is allowed only after the
//! selected platform artifact has been verified as a prebuilt production
//! artifact. Development commands are deliberately not represented as a
//! launch fallback.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{bail, Context, Result as AnyResult};
use log::error;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, State};

use crate::config::AppConfig;

const CATALOG_SCHEMA: &str = "io.tobkiri.launcher.presentation-catalog.v1";
const SHELL_CONTRACT_ID: &str = "app.shell.v1";
const SELECTION_DIR: &str = "presentation";
const SELECTION_FILE: &str = "selection.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PresentationApproval {
    pub state: String,
    pub provider_trust: String,
    pub grant_state: String,
    pub authority_mode: String,
    pub execution_domain: String,
    pub effect_scope: Vec<String>,
    pub blast_radius: String,
    #[serde(default)]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BasePackDescriptor {
    pub pack_id: String,
    pub display_name: String,
    pub version: String,
    pub artifact_digest: String,
    pub required_capabilities: Vec<String>,
    pub allowed_families: Vec<String>,
    pub approval: PresentationApproval,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PresentationContribution {
    pub contribution_id: String,
    pub contract_id: String,
    pub family: String,
    pub label: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArtifactVariant {
    pub artifact_id: String,
    pub variant: String,
    pub platform: String,
    pub architecture: String,
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub sha256: Option<String>,
    pub prebuilt: bool,
    pub production: bool,
    #[serde(default)]
    pub development_command: Option<String>,
    #[serde(default)]
    pub bundle_identifier: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PresentationArtifact {
    pub artifact_id: String,
    pub variant: String,
    pub platform: String,
    pub architecture: String,
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub sha256: Option<String>,
    pub prebuilt: bool,
    pub production: bool,
    #[serde(default)]
    pub development_command: Option<String>,
    #[serde(default)]
    pub bundle_identifier: Option<String>,
    pub status: String,
    pub status_detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellProviderDescriptor {
    pub provider_id: String,
    pub display_name: String,
    pub contract_id: String,
    pub contract_revision_digest: String,
    pub experience_role: String,
    pub presentation_kind: String,
    pub presentation_family: String,
    pub technology: String,
    pub capabilities: Vec<String>,
    pub contributions: Vec<PresentationContribution>,
    pub artifact_variants: Vec<ArtifactVariant>,
    #[serde(default)]
    pub artifact: Option<PresentationArtifact>,
    pub approval: PresentationApproval,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PresentationCatalog {
    pub schema: String,
    pub base_packs: Vec<BasePackDescriptor>,
    pub shell_providers: Vec<ShellProviderDescriptor>,
    #[serde(default)]
    pub generated_at: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PresentationSelection {
    pub base_pack_id: String,
    pub shell_provider_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PresentationMaterialization {
    pub status: String,
    #[serde(default)]
    pub base_pack_id: Option<String>,
    #[serde(default)]
    pub shell_provider_id: Option<String>,
    pub selected_contributions: Vec<PresentationContribution>,
    #[serde(default)]
    pub artifact: Option<PresentationArtifact>,
    #[serde(default)]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PresentationState {
    pub catalog: PresentationCatalog,
    #[serde(default)]
    pub selection: Option<PresentationSelection>,
    pub materialization: PresentationMaterialization,
}

#[derive(Debug, Clone, Serialize)]
pub struct PresentationLaunchResponse {
    pub status: String,
    pub provider_id: String,
    pub artifact_id: String,
    pub message: String,
}

#[tauri::command]
pub fn get_presentation_catalog(config: State<'_, AppConfig>) -> Result<PresentationState, String> {
    build_state(config.inner()).map_err(|error| format!("{error:#}"))
}

#[tauri::command]
pub fn select_presentation(
    config: State<'_, AppConfig>,
    selection: PresentationSelection,
) -> Result<PresentationState, String> {
    select_presentation_impl(config.inner(), selection).map_err(|error| format!("{error:#}"))
}

#[tauri::command]
pub fn launch_selected_presentation(
    _app: AppHandle,
    config: State<'_, AppConfig>,
) -> Result<PresentationLaunchResponse, String> {
    launch_selected_presentation_impl(config.inner()).map_err(|error| {
        error!("selected presentation launch blocked: {error:#}");
        format!("{error:#}")
    })
}

fn select_presentation_impl(
    config: &AppConfig,
    selection: PresentationSelection,
) -> AnyResult<PresentationState> {
    let mut catalog = load_catalog(config)?;
    validate_selection(&catalog, &selection)?;
    write_selection(config, &selection)?;
    catalog.generated_at = now_seconds();
    build_state_from_catalog(config, catalog, Some(selection))
}

fn launch_selected_presentation_impl(config: &AppConfig) -> AnyResult<PresentationLaunchResponse> {
    let state = build_state(config)?;
    let selection = state
        .selection
        .as_ref()
        .context("no Base Pack and Shell selection has been saved")?;
    if state.materialization.status != "materialized" {
        bail!(
            "selected presentation launch is blocked: {}",
            state
                .materialization
                .reason
                .as_deref()
                .unwrap_or("materialization did not complete")
        );
    }

    let shell = state
        .catalog
        .shell_providers
        .iter()
        .find(|candidate| candidate.provider_id == selection.shell_provider_id)
        .context("selected Shell Provider is no longer in the verified catalog")?;
    let artifact = shell
        .artifact
        .as_ref()
        .context("selected Shell Provider has no platform artifact")?;
    validate_production_artifact(artifact)?;
    let artifact_path = artifact_path(config, artifact)?;

    // The only launch input is a verified artifact path. No shell string,
    // package-manager command, or caller-provided arguments reach the process
    // boundary.
    open::that_detached(&artifact_path).with_context(|| {
        format!(
            "failed to launch verified Shell artifact {}",
            artifact_path.display()
        )
    })?;

    Ok(PresentationLaunchResponse {
        status: "launched".to_string(),
        provider_id: shell.provider_id.clone(),
        artifact_id: artifact.artifact_id.clone(),
        message: format!(
            "{} launched from its verified production artifact.",
            shell.display_name
        ),
    })
}

fn build_state(config: &AppConfig) -> AnyResult<PresentationState> {
    let catalog = load_catalog(config)?;
    let selection = read_selection(config)?;
    build_state_from_catalog(config, catalog, selection)
}

fn build_state_from_catalog(
    config: &AppConfig,
    mut catalog: PresentationCatalog,
    selection: Option<PresentationSelection>,
) -> AnyResult<PresentationState> {
    catalog.generated_at = now_seconds();
    for shell in &mut catalog.shell_providers {
        shell.artifact = Some(resolve_artifact(config, shell)?);
    }

    let materialization = match selection.as_ref() {
        Some(selection) => materialize_selection(&catalog, selection),
        None => PresentationMaterialization {
            status: "not_selected".to_string(),
            base_pack_id: None,
            shell_provider_id: None,
            selected_contributions: Vec::new(),
            artifact: None,
            reason: Some("Choose a Base Pack and a compatible Shell Provider.".to_string()),
        },
    };

    Ok(PresentationState {
        catalog,
        selection,
        materialization,
    })
}

fn load_catalog(config: &AppConfig) -> AnyResult<PresentationCatalog> {
    let path = config
        .app_dir
        .join("bundled")
        .join("presentation_catalog.json");
    let raw = match fs::read_to_string(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            include_str!("../bundled/presentation_catalog.json").to_string()
        }
        Err(error) => {
            return Err(error).with_context(|| {
                format!("failed to read presentation catalog at {}", path.display())
            })
        }
    };
    let catalog: PresentationCatalog = serde_json::from_str(&raw)
        .with_context(|| "presentation catalog is malformed and was rejected")?;
    if catalog.schema != CATALOG_SCHEMA {
        bail!(
            "unsupported presentation catalog schema: {}",
            catalog.schema
        );
    }
    if catalog.base_packs.is_empty() || catalog.shell_providers.is_empty() {
        bail!("presentation catalog must contain a Base Pack and Shell Provider");
    }
    Ok(catalog)
}

fn validate_selection(
    catalog: &PresentationCatalog,
    selection: &PresentationSelection,
) -> AnyResult<()> {
    let base_pack = catalog
        .base_packs
        .iter()
        .find(|base_pack| base_pack.pack_id == selection.base_pack_id)
        .context("selected Base Pack is unavailable")?;
    let shell = catalog
        .shell_providers
        .iter()
        .find(|shell| shell.provider_id == selection.shell_provider_id)
        .context("selected Shell Provider is unavailable")?;

    if shell.contract_id != SHELL_CONTRACT_ID {
        bail!(
            "selected Shell Provider implements {}, expected {}",
            shell.contract_id,
            SHELL_CONTRACT_ID
        );
    }
    if !base_pack
        .allowed_families
        .iter()
        .any(|family| family == &shell.presentation_family)
    {
        bail!("selected Shell Provider is not compatible with the Base Pack presentation family");
    }
    let missing = base_pack
        .required_capabilities
        .iter()
        .filter(|required| {
            !shell
                .capabilities
                .iter()
                .any(|provided| provided == *required)
        })
        .cloned()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        bail!(
            "selected Shell Provider is missing required capabilities: {}",
            missing.join(", ")
        );
    }
    if base_pack.approval.state == "blocked" || shell.approval.state == "blocked" {
        bail!("selected Base Pack or Shell Provider is blocked by approval state");
    }
    if base_pack.approval.state != "verified"
        || base_pack.approval.provider_trust != "verified"
        || shell.approval.state != "verified"
        || shell.approval.provider_trust != "verified"
    {
        bail!("selected Base Pack or Shell Provider is not verified for production use");
    }
    Ok(())
}

fn materialize_selection(
    catalog: &PresentationCatalog,
    selection: &PresentationSelection,
) -> PresentationMaterialization {
    let base_pack = catalog
        .base_packs
        .iter()
        .find(|base_pack| base_pack.pack_id == selection.base_pack_id);
    let shell = catalog
        .shell_providers
        .iter()
        .find(|shell| shell.provider_id == selection.shell_provider_id);
    let Some(base_pack) = base_pack else {
        return blocked_materialization(selection, "selected Base Pack is unavailable");
    };
    let Some(shell) = shell else {
        return blocked_materialization(selection, "selected Shell Provider is unavailable");
    };
    if let Err(error) = validate_selection(catalog, selection) {
        return blocked_materialization(selection, &error.to_string());
    }

    let contributions = shell
        .contributions
        .iter()
        .filter(|contribution| contribution.family == shell.presentation_family)
        .cloned()
        .collect::<Vec<_>>();
    let artifact = shell.artifact.clone();
    let Some(artifact) = artifact else {
        return blocked_materialization(
            selection,
            "selected Shell Provider has no platform artifact",
        );
    };
    if artifact.status != "verified" {
        return PresentationMaterialization {
            status: "blocked".to_string(),
            base_pack_id: Some(base_pack.pack_id.clone()),
            shell_provider_id: Some(shell.provider_id.clone()),
            selected_contributions: contributions,
            artifact: Some(artifact.clone()),
            reason: Some(format!(
                "Production launch requires a verified prebuilt artifact: {}",
                artifact.status_detail
            )),
        };
    }

    PresentationMaterialization {
        status: "materialized".to_string(),
        base_pack_id: Some(base_pack.pack_id.clone()),
        shell_provider_id: Some(shell.provider_id.clone()),
        selected_contributions: contributions,
        artifact: Some(artifact),
        reason: None,
    }
}

fn blocked_materialization(
    selection: &PresentationSelection,
    reason: &str,
) -> PresentationMaterialization {
    PresentationMaterialization {
        status: "blocked".to_string(),
        base_pack_id: Some(selection.base_pack_id.clone()),
        shell_provider_id: Some(selection.shell_provider_id.clone()),
        selected_contributions: Vec::new(),
        artifact: None,
        reason: Some(reason.to_string()),
    }
}

fn resolve_artifact(
    config: &AppConfig,
    shell: &ShellProviderDescriptor,
) -> AnyResult<PresentationArtifact> {
    let platform = current_platform();
    let architecture = current_architecture();
    let Some(variant) = shell
        .artifact_variants
        .iter()
        .find(|candidate| candidate.platform == platform && candidate.architecture == architecture)
    else {
        return Ok(PresentationArtifact {
            artifact_id: shell.provider_id.clone(),
            variant: format!("{platform}-{architecture}"),
            platform: platform.to_string(),
            architecture: architecture.to_string(),
            path: None,
            sha256: None,
            prebuilt: false,
            production: false,
            development_command: None,
            bundle_identifier: None,
            status: "unsupported_platform".to_string(),
            status_detail: format!(
                "No exact {}-{} artifact is declared.",
                platform, architecture
            ),
        });
    };

    let mut artifact = PresentationArtifact {
        artifact_id: variant.artifact_id.clone(),
        variant: variant.variant.clone(),
        platform: variant.platform.clone(),
        architecture: variant.architecture.clone(),
        path: variant.path.clone(),
        sha256: variant.sha256.clone(),
        prebuilt: variant.prebuilt,
        production: variant.production,
        development_command: variant.development_command.clone(),
        bundle_identifier: variant.bundle_identifier.clone(),
        status: "unverified".to_string(),
        status_detail: "Artifact has not passed production verification.".to_string(),
    };

    if artifact
        .development_command
        .as_deref()
        .is_some_and(|command| !command.trim().is_empty())
    {
        artifact.status = "development_only".to_string();
        artifact.status_detail =
            "Development commands are never a production launch fallback.".to_string();
        return Ok(artifact);
    }
    if !artifact.prebuilt || !artifact.production {
        artifact.status = "development_only".to_string();
        artifact.status_detail =
            "Only completed prebuilt production artifacts may launch.".to_string();
        return Ok(artifact);
    }
    let Some(path) = artifact.path.as_deref() else {
        artifact.status = "missing".to_string();
        artifact.status_detail = "The verified production artifact is not installed.".to_string();
        return Ok(artifact);
    };
    let Some(expected_digest) = artifact.sha256.as_deref() else {
        artifact.status_detail =
            "Artifact digest is missing; verification is required.".to_string();
        return Ok(artifact);
    };
    let path = match safe_artifact_path(config, path) {
        Ok(path) => path,
        Err(error) => {
            artifact.status_detail = format!("Artifact path rejected: {error}");
            return Ok(artifact);
        }
    };
    if !path.exists() {
        artifact.status = "missing".to_string();
        artifact.status_detail = "The verified production artifact is not installed.".to_string();
        return Ok(artifact);
    }
    let actual_digest = match sha256_path(&path) {
        Ok(digest) => digest,
        Err(error) => {
            artifact.status_detail = format!("Artifact could not be hashed: {error}");
            return Ok(artifact);
        }
    };
    if normalize_digest(expected_digest) != actual_digest {
        artifact.status = "digest_mismatch".to_string();
        artifact.status_detail = "Artifact digest does not match the pinned variant.".to_string();
        return Ok(artifact);
    }

    artifact.status = "verified".to_string();
    artifact.status_detail =
        "Pinned digest, prebuilt status, and production metadata verified.".to_string();
    Ok(artifact)
}

fn validate_production_artifact(artifact: &PresentationArtifact) -> AnyResult<()> {
    if let Some(command) = artifact.development_command.as_deref() {
        reject_development_command(Some(command))?;
    }
    if !artifact.prebuilt || !artifact.production {
        bail!("production launch requires a completed prebuilt artifact");
    }
    if artifact.status != "verified" {
        bail!(
            "production artifact verification status is {}",
            artifact.status
        );
    }
    Ok(())
}

pub(crate) fn reject_development_command(command: Option<&str>) -> AnyResult<()> {
    let Some(command) = command.map(str::trim).filter(|command| !command.is_empty()) else {
        return Ok(());
    };
    let normalized = command.to_ascii_lowercase();
    let development_markers = [
        "cargo tauri dev",
        "npm run dev",
        "pnpm dev",
        "yarn dev",
        "vite",
        "cargo run",
        "npm install",
        "pnpm install",
        "yarn install",
    ];
    if development_markers
        .iter()
        .any(|marker| normalized.contains(marker))
    {
        bail!("development command is not allowed in Production: {command}");
    }
    bail!("arbitrary commands are not allowed in Production launch metadata: {command}");
}

fn artifact_path(config: &AppConfig, artifact: &PresentationArtifact) -> AnyResult<PathBuf> {
    let relative = artifact
        .path
        .as_deref()
        .context("verified artifact has no path")?;
    let path = safe_artifact_path(config, relative)?;
    if !path.exists() {
        bail!(
            "verified artifact is no longer present at {}",
            path.display()
        );
    }
    let digest = sha256_path(&path)?;
    let expected = artifact
        .sha256
        .as_deref()
        .context("verified artifact has no digest")?;
    if normalize_digest(expected) != digest {
        bail!("verified artifact changed after materialization");
    }
    Ok(path)
}

fn safe_artifact_path(config: &AppConfig, relative: &str) -> AnyResult<PathBuf> {
    let relative_path = Path::new(relative);
    if relative_path.is_absolute()
        || relative_path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        bail!("artifact path must be relative to the bundled application root");
    }
    let root = config.app_dir.canonicalize().with_context(|| {
        format!(
            "bundled application root is unavailable: {}",
            config.app_dir.display()
        )
    })?;
    let candidate = root.join(relative_path);
    let metadata = match fs::symlink_metadata(&candidate) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(candidate),
        Err(error) => {
            return Err(error).with_context(|| {
                format!("failed to inspect artifact path: {}", candidate.display())
            })
        }
    };
    if metadata.file_type().is_symlink() {
        bail!("symlinked artifact entry is not accepted");
    }
    let canonical = candidate
        .canonicalize()
        .with_context(|| format!("artifact path is unavailable: {}", candidate.display()))?;
    if !canonical.starts_with(&root) {
        bail!("artifact path escapes the bundled application root");
    }
    Ok(canonical)
}

fn write_selection(config: &AppConfig, selection: &PresentationSelection) -> AnyResult<()> {
    let directory = config.user_data_dir.join(SELECTION_DIR);
    fs::create_dir_all(&directory).with_context(|| {
        format!(
            "failed to create presentation state directory {}",
            directory.display()
        )
    })?;
    let path = directory.join(SELECTION_FILE);
    let temporary = directory.join(format!(".selection-{}.tmp", std::process::id()));
    let bytes =
        serde_json::to_vec_pretty(selection).context("failed to encode presentation selection")?;
    let result = (|| -> AnyResult<()> {
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options
            .open(&temporary)
            .with_context(|| format!("failed to create {}", temporary.display()))?;
        file.write_all(&bytes)
            .context("failed to write presentation selection")?;
        file.sync_all()
            .context("failed to sync presentation selection")?;
        replace_file(&temporary, &path).with_context(|| {
            format!(
                "failed to commit presentation selection at {}",
                path.display()
            )
        })?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> io::Result<()> {
    fs::rename(source, destination)
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> io::Result<()> {
    // Windows does not let std::fs::rename replace an existing file. Remove
    // only the exact launcher-owned selection file; a failed replacement still
    // leaves no partially written selection.
    if destination.exists() {
        fs::remove_file(destination)?;
    }
    fs::rename(source, destination)
}

fn read_selection(config: &AppConfig) -> AnyResult<Option<PresentationSelection>> {
    let path = config
        .user_data_dir
        .join(SELECTION_DIR)
        .join(SELECTION_FILE);
    match fs::read_to_string(&path) {
        Ok(raw) => {
            Ok(Some(serde_json::from_str(&raw).with_context(|| {
                "saved presentation selection is malformed"
            })?))
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error).with_context(|| format!("failed to read {}", path.display())),
    }
}

fn sha256_path(path: &Path) -> AnyResult<String> {
    let mut hasher = Sha256::new();
    hash_path_contents(path, Path::new(""), &mut hasher)?;
    Ok(hex::encode(hasher.finalize()))
}

fn hash_path_contents(path: &Path, relative: &Path, hasher: &mut Sha256) -> AnyResult<()> {
    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("failed to inspect artifact path {}", path.display()))?;
    if metadata.file_type().is_symlink() {
        bail!("symlinked artifact content is not accepted");
    }
    if metadata.is_file() {
        hasher.update(relative.to_string_lossy().as_bytes());
        hasher.update([0]);
        let mut file = File::open(path)
            .with_context(|| format!("failed to open artifact file {}", path.display()))?;
        let mut buffer = [0_u8; 64 * 1024];
        loop {
            let read = file
                .read(&mut buffer)
                .context("failed to read artifact file")?;
            if read == 0 {
                break;
            }
            hasher.update(&buffer[..read]);
        }
        return Ok(());
    }
    if !metadata.is_dir() {
        bail!("artifact path is neither a file nor a directory");
    }
    let mut entries = fs::read_dir(path)
        .with_context(|| format!("failed to read artifact directory {}", path.display()))?
        .collect::<Result<Vec<_>, io::Error>>()?;
    entries.sort_by_key(|entry| entry.file_name());
    for entry in entries {
        let child_relative = relative.join(entry.file_name());
        hash_path_contents(&entry.path(), &child_relative, hasher)?;
    }
    Ok(())
}

fn normalize_digest(value: &str) -> String {
    value
        .trim()
        .strip_prefix("sha256:")
        .unwrap_or(value.trim())
        .to_ascii_lowercase()
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

fn now_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn sample_catalog() -> PresentationCatalog {
        PresentationCatalog {
            schema: CATALOG_SCHEMA.to_string(),
            base_packs: vec![BasePackDescriptor {
                pack_id: "defaults-basepack".into(),
                display_name: "Defaults Base Pack".into(),
                version: "4.0.0".into(),
                artifact_digest: "sha256:base".into(),
                required_capabilities: vec!["navigation".into(), "commands".into()],
                allowed_families: vec!["graphical".into(), "terminal".into()],
                approval: sample_approval("none"),
            }],
            shell_providers: vec![ShellProviderDescriptor {
                provider_id: "shell.tauri.default".into(),
                display_name: "Tauri Desktop".into(),
                contract_id: SHELL_CONTRACT_ID.into(),
                contract_revision_digest: "sha256:shell-contract".into(),
                experience_role: "shell".into(),
                presentation_kind: "packaged_process".into(),
                presentation_family: "graphical".into(),
                technology: "tauri".into(),
                capabilities: vec!["navigation".into(), "commands".into()],
                contributions: vec![PresentationContribution {
                    contribution_id: "ui.route.contribution.v1".into(),
                    contract_id: "ui.route.contribution.v1".into(),
                    family: "graphical".into(),
                    label: "Graphical routes".into(),
                }],
                artifact_variants: Vec::new(),
                artifact: None,
                approval: sample_approval("lease_only"),
            }],
            generated_at: 0,
        }
    }

    fn sample_approval(authority_mode: &str) -> PresentationApproval {
        PresentationApproval {
            state: "verified".into(),
            provider_trust: "verified".into(),
            grant_state: "not_minted".into(),
            authority_mode: authority_mode.into(),
            execution_domain: "test-domain".into(),
            effect_scope: Vec::new(),
            blast_radius: "No ambient Host authority.".into(),
            reason: None,
        }
    }

    #[test]
    fn production_rejects_known_development_commands() {
        for command in ["cargo tauri dev", "npm run dev", "pnpm dev"] {
            let error = reject_development_command(Some(command)).unwrap_err();
            assert!(error.to_string().contains("not allowed in Production"));
        }
    }

    #[test]
    fn production_rejects_all_arbitrary_commands_even_if_not_known_dev_command() {
        let error = reject_development_command(Some("./launcher --profile default")).unwrap_err();
        assert!(error.to_string().contains("arbitrary commands"));
        assert!(reject_development_command(None).is_ok());
    }

    #[test]
    fn selection_requires_exact_shell_contract_and_capabilities() {
        let mut catalog = sample_catalog();
        let selection = PresentationSelection {
            base_pack_id: "defaults-basepack".into(),
            shell_provider_id: "shell.tauri.default".into(),
        };
        assert!(validate_selection(&catalog, &selection).is_ok());

        catalog.shell_providers[0].contract_id = "wrong.contract.v1".into();
        let error = validate_selection(&catalog, &selection).unwrap_err();
        assert!(error.to_string().contains("expected app.shell.v1"));

        catalog.shell_providers[0].contract_id = SHELL_CONTRACT_ID.into();
        catalog.base_packs[0]
            .required_capabilities
            .push("windows".into());
        let error = validate_selection(&catalog, &selection).unwrap_err();
        assert!(error.to_string().contains("missing required capabilities"));

        catalog.base_packs[0].required_capabilities.pop();
        catalog.shell_providers[0].approval.state = "pending".into();
        let error = validate_selection(&catalog, &selection).unwrap_err();
        assert!(error
            .to_string()
            .contains("not verified for production use"));
    }

    #[test]
    fn materialization_filters_contributions_to_selected_presentation_family() {
        let mut catalog = sample_catalog();
        catalog.shell_providers[0]
            .contributions
            .push(PresentationContribution {
                contribution_id: "cli.command.contribution.v1".into(),
                contract_id: "cli.command.contribution.v1".into(),
                family: "terminal".into(),
                label: "CLI commands".into(),
            });
        catalog.shell_providers[0].artifact = Some(PresentationArtifact {
            artifact_id: "shell-tauri-test".into(),
            variant: "test".into(),
            platform: current_platform().into(),
            architecture: current_architecture().into(),
            path: None,
            sha256: None,
            prebuilt: true,
            production: true,
            development_command: None,
            bundle_identifier: None,
            status: "verified".into(),
            status_detail: "test".into(),
        });
        let selection = PresentationSelection {
            base_pack_id: "defaults-basepack".into(),
            shell_provider_id: "shell.tauri.default".into(),
        };
        let materialization = materialize_selection(&catalog, &selection);
        assert_eq!(materialization.status, "materialized");
        assert_eq!(materialization.selected_contributions.len(), 1);
        assert_eq!(
            materialization.selected_contributions[0].family,
            "graphical"
        );
    }

    #[test]
    fn directory_digest_is_deterministic_and_rejects_symlinks() {
        let root =
            std::env::temp_dir().join(format!("tobkiri-presentation-test-{}", std::process::id()));
        fs::remove_dir_all(&root).ok();
        fs::create_dir_all(root.join("bundle")).unwrap();
        fs::write(root.join("bundle").join("b.txt"), "b").unwrap();
        fs::write(root.join("bundle").join("a.txt"), "a").unwrap();
        let first = sha256_path(&root.join("bundle")).unwrap();
        let second = sha256_path(&root.join("bundle")).unwrap();
        assert_eq!(first, second);
        #[cfg(unix)]
        std::os::unix::fs::symlink(root.join("a.txt"), root.join("bundle").join("link")).unwrap();
        #[cfg(unix)]
        assert!(sha256_path(&root.join("bundle")).is_err());
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn normalize_digest_accepts_sha256_prefix() {
        let mut values = BTreeMap::new();
        values.insert(normalize_digest("sha256:ABC"), true);
        values.insert(normalize_digest(" abc "), true);
        assert_eq!(values.len(), 1);
    }
}
