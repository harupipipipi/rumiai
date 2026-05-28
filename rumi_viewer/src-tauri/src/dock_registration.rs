//! Dock registration: generate a macOS .app bundle for defaultspack.

use std::ffi::OsString;
use std::fs;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, bail, Context, Result as AnyResult};
use log::{error, info};
use serde_json::Value;

use crate::config::AppConfig;
use crate::process_utils;

const DEFAULTSPACK_DEFAULT_PORT: u16 = 8766;
const DEFAULTSPACK_READY_TIMEOUT: Duration = Duration::from_secs(60);
const DEFAULTSPACK_READY_POLL_INTERVAL: Duration = Duration::from_millis(250);

#[derive(Debug, Clone)]
struct DefaultspackDesktopMetadata {
    command: String,
    app_working_dir: PathBuf,
    env_vars: Vec<(String, String)>,
    port: u16,
}

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

fn is_valid_env_key(key: &str) -> bool {
    let mut chars = key.chars();
    match chars.next() {
        Some(first) if first == '_' || first.is_ascii_alphabetic() => {}
        _ => return false,
    }
    chars.all(|ch| ch == '_' || ch.is_ascii_alphanumeric())
}

fn read_desktop_app_env(desktop_app: &Value) -> AnyResult<Vec<(String, String)>> {
    let Some(env) = desktop_app.get("env") else {
        return Ok(Vec::new());
    };
    let env = env
        .as_object()
        .context("desktop_app.env must be an object")?;
    let mut entries = Vec::with_capacity(env.len());
    for (key, value) in env {
        if !is_valid_env_key(key) {
            bail!("desktop_app.env contains invalid shell variable name: {key}");
        }
        let value = value
            .as_str()
            .with_context(|| format!("desktop_app.env.{key} must be a string"))?;
        entries.push((key.clone(), value.to_string()));
    }
    entries.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(entries)
}

fn shell_quote(value: &str) -> String {
    if value.is_empty() {
        return "''".to_string();
    }
    format!("'{}'", value.replace('\'', "'\\''"))
}

fn shell_quote_path(path: &Path) -> String {
    shell_quote(&path.to_string_lossy())
}

fn venv_bin_dir(venv_dir: &Path) -> PathBuf {
    if cfg!(target_os = "windows") {
        venv_dir.join("Scripts")
    } else {
        venv_dir.join("bin")
    }
}

fn kernel_command_for_python(python: &Path) -> String {
    format!("{} -m app", shell_quote_path(python))
}

fn kernel_command_for_venv(venv_dir: &Path) -> String {
    let python = if cfg!(target_os = "windows") {
        venv_dir.join("Scripts").join("python.exe")
    } else {
        venv_dir.join("bin").join("python3")
    };
    kernel_command_for_python(&python)
}

fn defaultspack_browser_url(port: u16) -> String {
    format!("http://localhost:{port}/chat")
}

fn defaultspack_health_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/health")
}

fn read_defaultspack_port(env_vars: &[(String, String)]) -> AnyResult<u16> {
    for key in ["RUMI_DEFAULTSPACK_PORT", "DEFAULTS_HTTP_PORT"] {
        if let Some((_, value)) = env_vars.iter().find(|(env_key, _)| env_key == key) {
            return value
                .parse::<u16>()
                .with_context(|| format!("{key} must be a TCP port, got {value:?}"));
        }
    }
    Ok(DEFAULTSPACK_DEFAULT_PORT)
}

fn check_defaultspack_http_ready(client: &reqwest::blocking::Client, port: u16) -> bool {
    client
        .get(defaultspack_health_url(port))
        .send()
        .is_ok_and(|response| response.status().is_success())
}

fn defaultspack_health_client() -> AnyResult<reqwest::blocking::Client> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(1))
        .build()
        .context("failed to build defaultspack health client")
}

fn is_defaultspack_http_ready(port: u16) -> bool {
    defaultspack_health_client()
        .map(|client| check_defaultspack_http_ready(&client, port))
        .unwrap_or(false)
}

fn wait_for_defaultspack_http_ready(port: u16, child: &mut Child) -> AnyResult<()> {
    let client = defaultspack_health_client()?;
    let deadline = Instant::now() + DEFAULTSPACK_READY_TIMEOUT;

    loop {
        if check_defaultspack_http_ready(&client, port) {
            return Ok(());
        }

        if let Some(status) = child
            .try_wait()
            .context("failed to inspect defaultspack launch process")?
        {
            bail!("Defaultspack exited before its local server was ready: {status}");
        }

        if Instant::now() >= deadline {
            bail!(
                "Defaultspack local server did not become ready at {} within {} seconds",
                defaultspack_health_url(port),
                DEFAULTSPACK_READY_TIMEOUT.as_secs()
            );
        }

        thread::sleep(DEFAULTSPACK_READY_POLL_INTERVAL);
    }
}

fn append_path_prefix(prefix: &Path, current_path: Option<OsString>) -> AnyResult<OsString> {
    let mut paths = vec![prefix.to_path_buf()];
    if let Some(current_path) = current_path {
        paths.extend(std::env::split_paths(&current_path));
    }
    std::env::join_paths(paths).map_err(|error| anyhow!("failed to build PATH: {error}"))
}

fn xml_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn build_launch_script(
    pack_shell: &Path,
    token_file: &Path,
    rumi_home: &Path,
    venv_dir: &Path,
    kernel_port: u16,
    app_working_dir: &Path,
    command: &str,
    env_vars: &[(String, String)],
) -> String {
    let env_exports = env_vars
        .iter()
        .map(|(key, value)| format!("export {key}={}", shell_quote(value)))
        .collect::<Vec<_>>()
        .join("\n");
    let env_exports = if env_exports.is_empty() {
        String::new()
    } else {
        format!("\n# Environment declared by defaultspack's desktop_app metadata.\n{env_exports}\n")
    };
    let kernel_command = kernel_command_for_venv(venv_dir);

    format!(
        r#"#!/bin/bash
RUMI_HOME={rumi_home}
VENV_DIR={venv_dir}
PACK_SHELL={pack_shell}
TOKEN_FILE={token_file}
APP_WORKING_DIR={app_working_dir}
DESKTOP_COMMAND={command}
KERNEL_COMMAND={kernel_command}

export PATH="$VENV_DIR/bin:$PATH"
export RUMI_HOME
{env_exports}
RUMI_API_TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null | tr -d '\n')
export RUMI_API_TOKEN

exec "$PACK_SHELL" run "defaultspack" \
  --command "$DESKTOP_COMMAND" \
  --port {kernel_port} \
  --kernel-cmd "$KERNEL_COMMAND" \
  --working-dir "$APP_WORKING_DIR" \
  --timeout 120
"#,
        rumi_home = shell_quote_path(rumi_home),
        venv_dir = shell_quote_path(venv_dir),
        pack_shell = shell_quote_path(pack_shell),
        token_file = shell_quote_path(token_file),
        app_working_dir = shell_quote_path(app_working_dir),
        command = shell_quote(command),
        kernel_command = shell_quote(&kernel_command),
        kernel_port = kernel_port,
        env_exports = env_exports,
    )
}

/// Generate a macOS .app bundle at `~/Applications/Rumi Defaultspack.app`.
fn create_macos_app_bundle(
    app_name: &str,
    pack_shell: &Path,
    token_file: &Path,
    rumi_home: &Path,
    venv_dir: &Path,
    kernel_port: u16,
    app_working_dir: &Path,
    command: &str,
    env_vars: &[(String, String)],
) -> AnyResult<PathBuf> {
    let safe_name = app_name.replace('/', "_");
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
    let escaped_app_name = xml_escape(app_name);
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
    <string>{escaped_app_name}</string>
    <key>CFBundleDisplayName</key>
    <string>{escaped_app_name}</string>
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
    let launch_script = build_launch_script(
        pack_shell,
        token_file,
        rumi_home,
        venv_dir,
        kernel_port,
        app_working_dir,
        command,
        env_vars,
    );
    fs::write(&launch_path, &launch_script)
        .with_context(|| format!("failed to write {}", launch_path.display()))?;

    // Make executable on Unix platforms. Windows still compiles this module,
    // but does not support POSIX mode bits.
    #[cfg(unix)]
    {
        let mut perms = fs::metadata(&launch_path)?.permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&launch_path, perms)?;
    }

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

pub(crate) fn register_defaultspack_dock_impl(config: &AppConfig) -> AnyResult<String> {
    let app_dir = ensure_defaultspack_app_bundle(config)?;

    info!("Dock registration complete: {}", app_dir.display());
    Ok(format!(
        "Registered 'Rumi Defaultspack' to Dock at {}",
        app_dir.display()
    ))
}

#[tauri::command]
pub fn launch_defaultspack_desktop(config: tauri::State<'_, AppConfig>) -> Result<String, String> {
    launch_defaultspack_desktop_impl(&config).map_err(|e| {
        error!("launch_defaultspack_desktop failed: {e:#}");
        format!("{e:#}")
    })
}

pub(crate) fn launch_defaultspack_desktop_impl(config: &AppConfig) -> AnyResult<String> {
    let metadata = read_defaultspack_desktop_metadata(config)?;
    let url = defaultspack_browser_url(metadata.port);

    if !is_defaultspack_http_ready(metadata.port) {
        let mut child = spawn_defaultspack_local_server(config, &metadata)?;
        wait_for_defaultspack_http_ready(metadata.port, &mut child)?;
        info!("Defaultspack local server is ready at {url}");
    } else {
        info!("Defaultspack local server is already ready at {url}");
    }

    open::that_detached(&url).with_context(|| format!("failed to open {url}"))?;
    info!("Opened defaultspack browser URL: {url}");
    Ok(format!("Opening Rumi Defaultspack at {url}"))
}

fn read_defaultspack_desktop_metadata(
    config: &AppConfig,
) -> AnyResult<DefaultspackDesktopMetadata> {
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
    let env_vars = read_desktop_app_env(&desktop_app)?;
    let port = read_defaultspack_port(&env_vars)?;

    Ok(DefaultspackDesktopMetadata {
        command,
        app_working_dir,
        env_vars,
        port,
    })
}

fn read_desktop_api_token_from_config(config: &AppConfig) -> AnyResult<String> {
    let token_path = config.desktop_api_token_path();
    if let Ok(token) = read_saved_desktop_api_token(&token_path) {
        return Ok(token);
    }

    let candidates = [
        config.user_data_dir.join("hmac_keys.json"),
        config.rumi_home.join("user_data").join("hmac_keys.json"),
    ];
    let mut last_error: Option<anyhow::Error> = None;
    for hmac_keys_path in candidates {
        if !hmac_keys_path.exists() {
            continue;
        }
        match read_desktop_api_token(&hmac_keys_path) {
            Ok(token) => return Ok(token),
            Err(error) => last_error = Some(error),
        }
    }
    if let Some(error) = last_error {
        return Err(error).with_context(|| {
            format!(
                "failed to read desktop API token. Start the Kernel or remove stale {}",
                token_path.display()
            )
        });
    }
    bail!(
        "hmac_keys.json not found. Start the Kernel first to generate API keys."
    )
}

fn read_saved_desktop_api_token(token_path: &Path) -> AnyResult<String> {
    let token = fs::read_to_string(token_path)
        .with_context(|| format!("failed to read {}", token_path.display()))?;
    let token = token.trim().to_string();
    if token.is_empty() {
        bail!("desktop API token is empty at {}", token_path.display());
    }
    Ok(token)
}

fn persist_desktop_api_token(config: &AppConfig, api_token: &str) -> AnyResult<PathBuf> {
    let token_path = config.desktop_api_token_path();
    if let Some(parent) = token_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&token_path, api_token)
        .with_context(|| format!("failed to write token to {}", token_path.display()))?;
    #[cfg(unix)]
    {
        let _ = fs::set_permissions(&token_path, fs::Permissions::from_mode(0o600));
    }
    info!("Desktop API token saved to {}", token_path.display());
    Ok(token_path)
}

fn spawn_defaultspack_local_server(
    config: &AppConfig,
    metadata: &DefaultspackDesktopMetadata,
) -> AnyResult<Child> {
    let pack_shell = config
        .pack_shell_path()
        .context("pack-shell binary not found. Build it with `cargo build` in pack-shell/")?;
    let api_token = read_desktop_api_token_from_config(config)?;
    let kernel_command = kernel_command_for_python(&config.venv_python());
    let path = append_path_prefix(&venv_bin_dir(&config.venv_dir), std::env::var_os("PATH"))?;

    let mut command = process_utils::command(&pack_shell);
    command
        .arg("run")
        .arg("defaultspack")
        .arg("--command")
        .arg(&metadata.command)
        .arg("--port")
        .arg(config.kernel_port.to_string())
        .arg("--kernel-cmd")
        .arg(kernel_command)
        .arg("--working-dir")
        .arg(&metadata.app_working_dir)
        .arg("--timeout")
        .arg("120")
        .arg("--api-token")
        .arg(&api_token)
        .env("PATH", path)
        .env("RUMI_HOME", &config.rumi_home)
        .env("RUMI_APP_DIR", &config.app_dir)
        .env("RUMI_USER_DATA", &config.user_data_dir)
        .env("RUMI_API_TOKEN", &api_token)
        .env("RUMI_DEFAULTSPACK_OPEN_BROWSER", "0")
        .current_dir(&metadata.app_working_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    for (key, value) in &metadata.env_vars {
        command.env(key, value);
    }

    command
        .spawn()
        .with_context(|| format!("failed to spawn {}", pack_shell.display()))
}

fn ensure_defaultspack_app_bundle(config: &AppConfig) -> AnyResult<PathBuf> {
    if !cfg!(target_os = "macos") {
        bail!("Defaultspack dock registration is only supported on macOS");
    }

    // 1. Resolve pack-shell
    let pack_shell = config
        .pack_shell_path()
        .context("pack-shell binary not found. Build it with `cargo build` in pack-shell/")?;

    // 2. Read ecosystem.json
    let metadata = read_defaultspack_desktop_metadata(config)?;

    // 3. Read HMAC key and save as desktop API token
    let api_token = read_desktop_api_token_from_config(config)?;

    let token_path = persist_desktop_api_token(config, &api_token)?;

    // 4. Generate .app bundle
    let app_name = "Rumi Defaultspack";
    let app_dir = create_macos_app_bundle(
        app_name,
        &pack_shell,
        &token_path,
        &config.rumi_home,
        &config.venv_dir,
        config.kernel_port,
        &metadata.app_working_dir,
        &metadata.command,
        &metadata.env_vars,
    )?;

    Ok(app_dir)
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
    fn read_saved_desktop_api_token_trims_file_contents() {
        let dir = std::env::temp_dir().join("rumi_dock_test_saved_token");
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join(".desktop_api_token");
        fs::write(&path, "saved-token\n").unwrap();
        let result = read_saved_desktop_api_token(&path).unwrap();
        assert_eq!(result, "saved-token");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn read_saved_desktop_api_token_rejects_empty_file() {
        let dir = std::env::temp_dir().join("rumi_dock_test_empty_saved_token");
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join(".desktop_api_token");
        fs::write(&path, "\n").unwrap();
        let result = read_saved_desktop_api_token(&path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("empty"));
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    #[cfg(unix)]
    fn shell_quote_escapes_paths_and_commands_in_launch_script() {
        let script = build_launch_script(
            Path::new("/tmp/Rumi's bin/pack-shell"),
            Path::new("/tmp/token file"),
            Path::new("/tmp/rumi home"),
            Path::new("/tmp/venv dir"),
            8767,
            Path::new("/tmp/work $(bad)"),
            "python -c \"print('hello')\"",
            &[("RUMI_DEFAULTSPACK_SURFACE".into(), "webview".into())],
        );

        assert!(script.contains("PACK_SHELL='/tmp/Rumi'\\''s bin/pack-shell'"));
        assert!(script.contains("TOKEN_FILE='/tmp/token file'"));
        assert!(script.contains("APP_WORKING_DIR='/tmp/work $(bad)'"));
        assert!(script.contains("DESKTOP_COMMAND='python -c \"print('\\''hello'\\'')\"'"));
        assert!(script.contains("KERNEL_COMMAND=''\\''/tmp/venv dir/bin/python3'\\'' -m app'"));
        assert!(script.contains("export RUMI_DEFAULTSPACK_SURFACE='webview'"));
        assert!(script.contains("--command \"$DESKTOP_COMMAND\""));
        assert!(script.contains("--port 8767"));
        assert!(script.contains("--kernel-cmd \"$KERNEL_COMMAND\""));
    }

    #[test]
    fn xml_escape_escapes_plist_values() {
        assert_eq!(
            xml_escape("Rumi & <Default> \"Pack\""),
            "Rumi &amp; &lt;Default&gt; &quot;Pack&quot;"
        );
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
    fn read_desktop_app_env_sorts_and_validates_env_vars() {
        let desktop_app: Value = serde_json::from_str(
            r#"{"env":{"RUMI_DEFAULTSPACK_SURFACE":"webview","DEFAULTS_HTTP_PORT":"8766"}}"#,
        )
        .unwrap();

        let env_vars = read_desktop_app_env(&desktop_app).unwrap();
        assert_eq!(
            env_vars,
            vec![
                ("DEFAULTS_HTTP_PORT".into(), "8766".into()),
                ("RUMI_DEFAULTSPACK_SURFACE".into(), "webview".into()),
            ]
        );
    }

    #[test]
    fn read_desktop_app_env_rejects_invalid_shell_names() {
        let desktop_app: Value = serde_json::from_str(r#"{"env":{"BAD;NAME":"oops"}}"#).unwrap();
        let err = read_desktop_app_env(&desktop_app).unwrap_err();
        assert!(err.to_string().contains("invalid shell variable name"));
    }

    #[test]
    fn read_defaultspack_port_prefers_rumi_specific_port() {
        let port = read_defaultspack_port(&[
            ("DEFAULTS_HTTP_PORT".into(), "8766".into()),
            ("RUMI_DEFAULTSPACK_PORT".into(), "9876".into()),
        ])
        .unwrap();
        assert_eq!(port, 9876);
    }

    #[test]
    fn read_defaultspack_port_defaults_when_env_is_absent() {
        assert_eq!(
            read_defaultspack_port(&[]).unwrap(),
            DEFAULTSPACK_DEFAULT_PORT
        );
    }

    #[test]
    fn read_defaultspack_port_rejects_invalid_port() {
        let err =
            read_defaultspack_port(&[("DEFAULTS_HTTP_PORT".into(), "nope".into())]).unwrap_err();
        assert!(err.to_string().contains("DEFAULTS_HTTP_PORT"));
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
