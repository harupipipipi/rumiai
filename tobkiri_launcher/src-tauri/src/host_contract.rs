//! Owner-only host contract for injecting scoped runtime values.
//!
//! Secrets are passed to the managed Python runtime through this file rather
//! than through a process environment variable.  The file is created below
//! the Launcher-owned user-data root with owner-only permissions and contains
//! only the values for the selected profile.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::config::AppConfig;

pub(crate) const CONTRACT_ENV: &str = "TOBKIRI_HOST_CONTRACT_PATH";

/// Exact identity of the execution Profile captured by the Host.
///
/// Every Launcher boundary that can cause code to execute carries this same
/// tuple. `profile_id` alone is not an authority binding: a revision, active
/// activation, or resolved plan can change while the user-facing Profile ID
/// stays the same.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub(crate) struct ExecutionProfileIdentity {
    pub(crate) profile_id: String,
    pub(crate) profile_revision: String,
    pub(crate) activation_id: String,
    pub(crate) plan_digest: String,
}

impl ExecutionProfileIdentity {
    /// Construct and validate one exact execution identity.
    pub(crate) fn new(
        profile_id: impl Into<String>,
        profile_revision: impl Into<String>,
        activation_id: impl Into<String>,
        plan_digest: impl Into<String>,
    ) -> Result<Self> {
        let identity = Self {
            profile_id: profile_id.into(),
            profile_revision: profile_revision.into(),
            activation_id: activation_id.into(),
            plan_digest: plan_digest.into(),
        };
        identity.validate()?;
        Ok(identity)
    }

    /// Reject malformed or incomplete identity material before it crosses a
    /// process, persistence, or approval boundary.
    pub(crate) fn validate(&self) -> Result<()> {
        validate_profile_id(&self.profile_id)?;
        validate_sha256(&self.profile_revision, "profile_revision")?;
        validate_activation_id(&self.activation_id)?;
        validate_sha256(&self.plan_digest, "plan_digest")?;
        Ok(())
    }

    /// Return whether two bindings identify exactly the same execution.
    pub(crate) fn matches(&self, other: &Self) -> bool {
        self == other
    }
}

/// The only place where the bundled Defaults identity is synthesized.
///
/// This is a bootstrap template for the first Kernel process and is never
/// accepted as the identity for a presentation launch or a guardian lease.
fn bootstrap_identity() -> ExecutionProfileIdentity {
    ExecutionProfileIdentity {
        profile_id: "defaults".into(),
        profile_revision: format!("sha256:{}", "0".repeat(64)),
        activation_id: "activation:bootstrap-template".into(),
        plan_digest: format!("sha256:{}", "0".repeat(64)),
    }
}

pub(crate) fn contract_path(config: &AppConfig) -> PathBuf {
    config.user_data_dir.join("host_contract.json")
}

/// Write the current host-bound values and return the contract path.
pub(crate) fn write_contract(
    config: &AppConfig,
    identity: &ExecutionProfileIdentity,
    values: impl IntoIterator<Item = (&'static str, String)>,
) -> Result<PathBuf> {
    identity.validate()?;
    let path = contract_path(config);
    let parent = path
        .parent()
        .context("host contract path has no parent directory")?;
    fs::create_dir_all(parent).with_context(|| {
        format!(
            "failed to create host contract directory {}",
            parent.display()
        )
    })?;
    restrict_owner_only(parent)?;

    let existing: Option<Value> = fs::read(&path)
        .ok()
        .and_then(|raw| serde_json::from_slice::<Value>(&raw).ok());
    let mut merged_values = existing_values_for_identity(existing.as_ref(), identity);
    for (name, value) in values {
        if !value.trim().is_empty() {
            merged_values.insert(name.to_string(), value);
        }
    }
    let mut payload = Map::new();
    payload.insert(
        "schema_version".into(),
        Value::String("tobkiri.host-contract.v1".into()),
    );
    payload.insert(
        "profile_id".into(),
        Value::String(identity.profile_id.clone()),
    );
    payload.insert(
        "profile_revision".into(),
        Value::String(identity.profile_revision.clone()),
    );
    payload.insert(
        "activation_id".into(),
        Value::String(identity.activation_id.clone()),
    );
    payload.insert(
        "plan_digest".into(),
        Value::String(identity.plan_digest.clone()),
    );
    payload.insert(
        "values".into(),
        serde_json::to_value(merged_values).context("failed to encode host contract values")?,
    );
    let body = serde_json::to_vec_pretty(&Value::Object(payload))?;
    let temporary = path.with_extension(format!("{}.tmp", std::process::id()));
    fs::write(&temporary, body)
        .with_context(|| format!("failed to write host contract {}", temporary.display()))?;
    restrict_owner_only_file(&temporary)?;
    fs::rename(&temporary, &path).with_context(|| {
        format!(
            "failed to publish host contract {} from {}",
            path.display(),
            temporary.display()
        )
    })?;
    restrict_owner_only_file(&path)?;
    Ok(path)
}

/// Write the bootstrap-only contract used while the Kernel is establishing a
/// canonical active capture. Normal Shell and guardian paths must call
/// `write_contract` with the authenticated active identity instead.
pub(crate) fn write_bootstrap_contract(
    config: &AppConfig,
    values: impl IntoIterator<Item = (&'static str, String)>,
) -> Result<PathBuf> {
    let identity = bootstrap_identity();
    write_contract(config, &identity, values)
}

fn existing_values_for_identity(
    existing: Option<&Value>,
    identity: &ExecutionProfileIdentity,
) -> BTreeMap<String, String> {
    let identity_matches = |payload: &&Value| {
        payload.get("profile_id").and_then(Value::as_str) == Some(identity.profile_id.as_str())
            && payload.get("profile_revision").and_then(Value::as_str)
                == Some(identity.profile_revision.as_str())
            && payload.get("activation_id").and_then(Value::as_str)
                == Some(identity.activation_id.as_str())
            && payload.get("plan_digest").and_then(Value::as_str)
                == Some(identity.plan_digest.as_str())
    };
    existing
        .filter(identity_matches)
        .and_then(|payload| payload.get("values").cloned())
        .and_then(|raw| serde_json::from_value(raw).ok())
        .unwrap_or_default()
}

/// Read the exact identity currently published in the Host contract.
pub(crate) fn read_identity(config: &AppConfig) -> Option<ExecutionProfileIdentity> {
    let path = contract_path(config);
    let payload: Value = serde_json::from_slice(&fs::read(path).ok()?).ok()?;
    identity_from_payload(&payload)
}

/// Read one contract value for Launcher-side verification without exposing the
/// entire document to logs or child process arguments.
pub(crate) fn read_value(config: &AppConfig, name: &str) -> Option<String> {
    let path = contract_path(config);
    let payload: Value = serde_json::from_slice(&fs::read(path).ok()?).ok()?;
    identity_from_payload(&payload)?;
    payload
        .get("values")?
        .get(name)?
        .as_str()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
}

fn identity_from_payload(payload: &Value) -> Option<ExecutionProfileIdentity> {
    ExecutionProfileIdentity::new(
        payload.get("profile_id")?.as_str()?.to_owned(),
        payload.get("profile_revision")?.as_str()?.to_owned(),
        payload.get("activation_id")?.as_str()?.to_owned(),
        payload.get("plan_digest")?.as_str()?.to_owned(),
    )
    .ok()
}

#[cfg(unix)]
fn restrict_owner_only(path: &Path) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;

    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("failed to inspect host contract path {}", path.display()))?;
    if metadata.file_type().is_symlink() {
        anyhow::bail!("refusing symlinked host contract path {}", path.display());
    }
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    Ok(())
}

#[cfg(unix)]
fn restrict_owner_only_file(path: &Path) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;

    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("failed to inspect host contract file {}", path.display()))?;
    if metadata.file_type().is_symlink() {
        anyhow::bail!("refusing symlinked host contract file {}", path.display());
    }
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    Ok(())
}

#[cfg(not(unix))]
fn restrict_owner_only_file(_path: &Path) -> Result<()> {
    Ok(())
}

#[cfg(not(unix))]
fn restrict_owner_only(_path: &Path) -> Result<()> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        existing_values_for_identity, read_identity, read_value, write_contract,
        ExecutionProfileIdentity,
    };
    use crate::config::AppConfig;
    use serde_json::json;
    use std::path::Path;

    fn identity(profile_id: &str, revision: &str, activation: &str) -> ExecutionProfileIdentity {
        ExecutionProfileIdentity::new(
            profile_id,
            format!("sha256:{}", revision.repeat(64)),
            format!("activation:{activation}template"),
            format!("sha256:{}", revision.repeat(64)),
        )
        .unwrap()
    }

    #[test]
    fn profile_or_revision_switch_does_not_reuse_existing_secret_values() {
        let active = identity("profile-a", "a", "active-");
        let existing = json!({
            "profile_id": "profile-a",
            "profile_revision": active.profile_revision.clone(),
            "activation_id": active.activation_id.clone(),
            "plan_digest": active.plan_digest.clone(),
            "values": {"desktop_api_token": "profile-a-secret"}
        });

        assert_eq!(
            existing_values_for_identity(Some(&existing), &active)
                .get("desktop_api_token")
                .map(String::as_str),
            Some("profile-a-secret")
        );
        assert!(existing_values_for_identity(
            Some(&existing),
            &identity("profile-b", "a", "active-")
        )
        .is_empty());
        assert!(existing_values_for_identity(
            Some(&existing),
            &identity("profile-a", "b", "active-")
        )
        .is_empty());
    }

    #[test]
    fn contract_publishes_and_reads_the_complete_execution_profile_identity() {
        let root =
            std::env::temp_dir().join(format!("tobkiri-host-contract-test-{}", std::process::id()));
        std::fs::remove_dir_all(&root).ok();
        let config = test_config(&root);
        let first = identity("profile-a", "a", "active-");
        write_contract(
            &config,
            &first,
            [("desktop_api_token", "profile-a-secret".into())],
        )
        .unwrap();
        assert_eq!(read_identity(&config), Some(first.clone()));
        assert_eq!(
            read_value(&config, "desktop_api_token").as_deref(),
            Some("profile-a-secret")
        );

        let second = identity("profile-a", "b", "rotated-");
        write_contract(&config, &second, []).unwrap();
        assert_eq!(read_identity(&config), Some(second));
        assert_eq!(read_value(&config, "desktop_api_token"), None);
        std::fs::remove_dir_all(root).unwrap();
    }

    fn test_config(root: &Path) -> AppConfig {
        AppConfig {
            app_dir: root.join("app"),
            rumi_home: root.join("app"),
            python_dir: root.join("python"),
            uv_path: root.join("uv"),
            venv_dir: root.join("venv"),
            user_data_dir: root.join("user_data"),
            log_dir: root.join("logs"),
            kernel_port: 8765,
            dev_workspace_root: None,
        }
    }
}

fn validate_profile_id(value: &str) -> Result<()> {
    let trimmed = value.trim();
    if trimmed != value
        || trimmed.is_empty()
        || trimmed.len() > 128
        || trimmed.chars().any(char::is_control)
        || trimmed.contains('/')
        || trimmed.contains('\\')
        || trimmed.contains("..")
    {
        anyhow::bail!("host contract profile_id is invalid");
    }
    Ok(())
}

fn validate_sha256(value: &str, label: &str) -> Result<()> {
    let digest = value
        .strip_prefix("sha256:")
        .with_context(|| format!("host contract {label} is not a sha256 digest"))?;
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        anyhow::bail!("host contract {label} is not a sha256 digest");
    }
    Ok(())
}

fn validate_activation_id(value: &str) -> Result<()> {
    let suffix = value
        .strip_prefix("activation:")
        .context("host contract activation_id is invalid")?;
    if !(8..=128).contains(&suffix.len())
        || !suffix.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        })
    {
        anyhow::bail!("host contract activation_id is invalid");
    }
    Ok(())
}
