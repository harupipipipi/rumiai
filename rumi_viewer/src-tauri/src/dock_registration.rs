//! Dock registration: generate a macOS .app bundle for defaultspack.

use std::fs;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result as AnyResult};
use log::{error, info};
use serde_json::Value;

use crate::config::AppConfig;

/// Read the HMAC key from the plaintext `hmac_keys.json` file.
///
/// Returns the first active key's `key` field. If the file uses Fernet
/// encryption, returns an error (caller should inform the user).
fn read_desktop_api_token(hmac_keys_path: &Path) -> AnyResult<String> {
    let raw = fs::read_to_string(hmac_keys_path)
        .with_context(|| format!("failed to read {}", hmac_keys_path.display()))?;
    let data: Value = serde_json::from_str(&raw)
        .with_context(|| format!("invalid JSON in {}", hmac_keys_path.display()))?;

    // Check for Fernet encryption wrapper
    if data.get("encryption").and_then(|v| v.as_str()) == Some("fernet") {
        bail!("HMAC keys are encrypted. Decrypt them first or set RUMI_SECURITY_MODE=permissive.");
    }

    let keys = data
        .get("keys")
        .and_then(|v| v.as_array())
        .context("hmac_keys.json missing 'keys' array")?;

    for key_entry in keys {
        if key_entry
            .get("is_active")
            .and_then(|v| v.as_bool())
            .is_some_and(|is_active| !is_active)
        {
            continue;
        }
        if let Some(key_str) = key_entry.get("key").and_then(|v| v.as_str()) {
            if !key_str.is_empty() {
                return Ok(key_str.to_string());
            }
        }
    }

    bail!("No active key found in hmac_keys.json")
}

/// Read the `desktop_app.command` from the defaultspack ecosystem.json.
fn read_desktop_app_command(ecosystem_path: &Path) -> AnyResult<(String, Value)> {
    let raw = fs::read_to_string(ecosystem_path)
        .with_context(|| format!("failed to read {}", ecosystem_path.display()))?;
    let data: Value = serde_json::from_str(&raw)
        .with_context(|| format!("invalid JSON in {}", ecosystem_path.display()))?;

    let desktop_app = data
        .get("desktop_app")
        .context("ecosystem.json missing 'desktop_app' section")?;

    let command = desktop_app
        .get("command")
        .and_then(|v| v.as_str())
        .context("desktop_app.command is missing")?
        .to_string();

    Ok((command, desktop_app.clone()))
}

fn resolve_desktop_app_working_dir(desktop_app: &Value, pack_root: &Path) -> PathBuf {
    let working_dir = desktop_app
        .get("working_dir")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim();
    if working_dir.is_empty() {
        return pack_root.to_path_buf();
    }

    let path = PathBuf::from(working_dir);
    if path.is_absolute() {
        path
    } else {
        pack_root.join(path)
    }
}

/// Generate a macOS .app bundle at `~/Applications/Rumi Defaultspack.app`.
fn create_macos_app_bundle(
    app_name: &str,
    pack_shell: &Path,
    token_file: &Path,
    rumi_home: &Path,
    venv_dir: &Path,
    app_working_dir: &Path,
    command: &str,
) -> AnyResult<PathBuf> {
    let safe_name = app_name.replace('/', "_").replace(' ', "_");
    let apps_base = dirs_home().join("Applications");
    fs::create_dir_all(&apps_base)
        .with_context(|| format!("failed to create {}", apps_base.display()))?;

    let app_dir = apps_base.join(format!("{safe_name}.app"));
    let contents_dir = app_dir.join("Contents");
    let macos_dir = contents_dir.join("MacOS");
    fs::create_dir_all(&macos_dir)
        .with_context(|| format!("failed to create {}", macos_dir.display()))?;

    // Info.plist
    let bundle_id = "ai.rumi.pack.defaultspack";
    let plist_path = contents_dir.join("Info.plist");
    let plist_content = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundleIdentifier</key>
    <string>{bundle_id}</string>
    <key>CFBundleName</key>
    <string>{app_name}</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>"#
    );
    fs::write(&plist_path, &plist_content)
        .with_context(|| format!("failed to write {}", plist_path.display()))?;

    // Launch script
    let launch_path = macos_dir.join("launch");
    let launch_script = format!(
        r#"#!/bin/bash
RUMI_HOME="{rumi_home}"
VENV_DIR="{venv_dir}"
PACK_SHELL="{pack_shell}"
TOKEN_FILE="{token_file}"

export PATH="$VENV_DIR/bin:$PATH"
export RUMI_HOME
RUMI_API_TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null | tr -d '\n')
export RUMI_API_TOKEN

exec "$PACK_SHELL" run "defaultspack" \
  --command "{command}" \
  --kernel-cmd "$VENV_DIR/bin/python3 -m app" \
  --working-dir "{app_working_dir}" \
  --timeout 120
"#,
        rumi_home = rumi_home.display(),
        venv_dir = venv_dir.display(),
        pack_shell = pack_shell.display(),
        token_file = token_file.display(),
        app_working_dir = app_working_dir.display(),
        command = command,
    );
    fs::write(&launch_path, &launch_script)
        .with_context(|| format!("failed to write {}", launch_path.display()))?;

    // Make executable
    let mut perms = fs::metadata(&launch_path)?.permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&launch_path, perms)?;

    Ok(app_dir)
}

fn dirs_home() -> PathBuf {
    dirs::home_dir().unwrap_or_else(|| PathBuf::from("/tmp"))
}

/// Tauri command: register defaultspack to the macOS Dock.
///
/// 1. Resolve pack-shell binary
/// 2. Read ecosystem.json → desktop_app.command
/// 3. Read HMAC key (plaintext only) → save to .desktop_api_token
/// 4. Generate ~/Applications/Rumi Defaultspack.app
#[tauri::command]
pub fn register_defaultspack_dock(config: tauri::State<'_, AppConfig>) -> Result<String, String> {
    register_defaultspack_dock_impl(&config).map_err(|e| {
        error!("register_defaultspack_dock failed: {e:#}");
        format!("{e:#}")
    })
}

fn register_defaultspack_dock_impl(config: &AppConfig) -> AnyResult<String> {
    if !cfg!(target_os = "macos") {
        bail!("Dock registration is only supported on macOS");
    }

    // 1. Resolve pack-shell
    let pack_shell = config
        .pack_shell_path()
        .context("pack-shell binary not found. Build it with `cargo build` in pack-shell/")?;

    // 2. Read ecosystem.json
    let ecosystem_path = config.defaultspack_ecosystem_json();
    if !ecosystem_path.exists() {
        bail!(
            "defaultspack ecosystem.json not found at {}",
            ecosystem_path.display()
        );
    }
    let (command, desktop_app) = read_desktop_app_command(&ecosystem_path)?;
    let pack_root = ecosystem_path
        .parent()
        .context("defaultspack ecosystem.json has no parent directory")?;
    let app_working_dir = resolve_desktop_app_working_dir(&desktop_app, pack_root);

    // 3. Read HMAC key and save as desktop API token
    let hmac_keys_path = config.rumi_home.join("user_data").join("hmac_keys.json");
    if !hmac_keys_path.exists() {
        bail!(
            "hmac_keys.json not found at {}. Start the Kernel first to generate API keys.",
            hmac_keys_path.display()
        );
    }
    let api_token = read_desktop_api_token(&hmac_keys_path)?;

    let token_path = config.desktop_api_token_path();
    if let Some(parent) = token_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&token_path, &api_token)
        .with_context(|| format!("failed to write token to {}", token_path.display()))?;
    // chmod 600
    #[cfg(unix)]
    {
        let _ = fs::set_permissions(&token_path, fs::Permissions::from_mode(0o600));
    }
    info!("Desktop API token saved to {}", token_path.display());

    // 4. Generate .app bundle
    let app_name = "Rumi Defaultspack";
    let app_dir = create_macos_app_bundle(
        app_name,
        &pack_shell,
        &token_path,
        &config.rumi_home,
        &config.venv_dir,
        &app_working_dir,
        &command,
    )?;

    info!("Dock registration complete: {}", app_dir.display());
    Ok(format!(
        "Registered '{}' to Dock at {}",
        app_name,
        app_dir.display()
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn read_desktop_api_token_rejects_encrypted() {
        let dir = std::env::temp_dir().join("rumi_dock_test_encrypted");
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("hmac_keys.json");
        fs::write(
            &path,
            r#"{"version":"1.0","encryption":"fernet","payload":"abc"}"#,
        )
        .unwrap();
        let result = read_desktop_api_token(&path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("encrypted"));
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn read_desktop_api_token_returns_first_key() {
        let dir = std::env::temp_dir().join("rumi_dock_test_plaintext");
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("hmac_keys.json");
        fs::write(
            &path,
            r#"{"version":"1.0","keys":[{"key":"test-token-123","created_at":1000}]}"#,
        )
        .unwrap();
        let result = read_desktop_api_token(&path).unwrap();
        assert_eq!(result, "test-token-123");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn read_desktop_api_token_skips_inactive_keys() {
        let dir = std::env::temp_dir().join("rumi_dock_test_active_key");
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("hmac_keys.json");
        fs::write(
            &path,
            r#"{"version":"1.0","keys":[{"key":"old-token","is_active":false},{"key":"active-token","is_active":true}]}"#,
        )
        .unwrap();
        let result = read_desktop_api_token(&path).unwrap();
        assert_eq!(result, "active-token");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn read_desktop_app_command_parses_ecosystem() {
        let dir = std::env::temp_dir().join("rumi_dock_test_eco");
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("ecosystem.json");
        fs::write(
            &path,
            r#"{"pack_id":"defaultspack","desktop_app":{"command":"python app.py"}}"#,
        )
        .unwrap();
        let (cmd, _) = read_desktop_app_command(&path).unwrap();
        assert_eq!(cmd, "python app.py");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn resolve_desktop_app_working_dir_defaults_to_pack_root() {
        let pack_root = PathBuf::from("/tmp/defaultspack");
        let desktop_app: Value = serde_json::from_str(r#"{"working_dir":""}"#).unwrap();
        assert_eq!(
            resolve_desktop_app_working_dir(&desktop_app, &pack_root),
            pack_root
        );
    }

    #[test]
    fn resolve_desktop_app_working_dir_joins_relative_path() {
        let pack_root = PathBuf::from("/tmp/defaultspack");
        let desktop_app: Value = serde_json::from_str(r#"{"working_dir":"apps"}"#).unwrap();
        assert_eq!(
            resolve_desktop_app_working_dir(&desktop_app, &pack_root),
            pack_root.join("apps")
        );
    }
}
