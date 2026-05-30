//! Path resolution and application configuration for Tauri.
//!
//! All paths are derived from Tauri's `resource_dir` and `app_data_dir`
//! so that the application works correctly when bundled.

use anyhow::Result;
use std::path::{Path, PathBuf};

/// Central configuration resolved from Tauri path APIs.
#[derive(Debug, Clone)]
pub struct AppConfig {
    /// `{resource_dir}/app` — bundled rumi_ai_1_10 contents (= kernel root).
    pub app_dir: PathBuf,
    /// Same as `app_dir` — the Kernel's working directory.
    pub rumi_home: PathBuf,
    /// `{app_data_dir}/python` — PBS standalone Python.
    pub python_dir: PathBuf,
    /// Path to the `uv` binary (downloaded location).
    pub uv_path: PathBuf,
    /// `{app_data_dir}/venv` — Python virtual-environment.
    pub venv_dir: PathBuf,
    /// `{app_data_dir}/user_data` — persistent user data.
    pub user_data_dir: PathBuf,
    /// `{app_data_dir}/logs` — log files.
    pub log_dir: PathBuf,
    /// Kernel HTTP port (default 8765).
    pub kernel_port: u16,
    /// Repo root when running against a development checkout.
    pub dev_workspace_root: Option<PathBuf>,
}

impl AppConfig {
    /// Detect configuration from Tauri-provided directories.
    ///
    /// Layout:
    /// ```text
    /// {resource_dir}/
    /// └── app/               ← bundled rumi_ai_1_10 contents
    ///     ├── app.py
    ///     ├── core_runtime/
    ///     ├── requirements.txt
    ///     └── bundled/
    ///         └── uv(.exe)   ← optional pre-bundled uv
    ///
    /// {app_data_dir}/
    /// ├── python/
    /// ├── uv(.exe)
    /// ├── venv/
    /// ├── user_data/
    /// └── logs/
    /// ```
    pub fn detect_for_tauri(resource_dir: PathBuf, app_data_dir: PathBuf) -> Result<Self> {
        let mut dev_workspace_root = None;
        let mut app_dir = resource_dir.join("app");
        if !app_dir.exists() {
            if let Some(workspace_root) = find_dev_workspace_root(&resource_dir) {
                let candidate = workspace_root.join("rumi_ai_1_10");
                if candidate.join("app.py").exists() {
                    app_dir = candidate;
                    dev_workspace_root = Some(workspace_root);
                }
            }
        }
        let rumi_home = app_dir.clone();

        let python_dir = app_data_dir.join("python");
        let uv_path = if cfg!(target_os = "windows") {
            app_data_dir.join("uv.exe")
        } else {
            app_data_dir.join("uv")
        };
        let venv_dir = app_data_dir.join("venv");
        let user_data_dir = app_data_dir.join("user_data");
        let log_dir = app_data_dir.join("logs");

        Ok(Self {
            app_dir,
            rumi_home,
            python_dir,
            uv_path,
            venv_dir,
            user_data_dir,
            log_dir,
            kernel_port: 8765,
            dev_workspace_root,
        })
    }

    /// Return the path to the Python binary inside the PBS directory.
    pub fn python_bin(&self) -> PathBuf {
        if cfg!(target_os = "windows") {
            self.python_dir.join("python.exe")
        } else {
            self.python_dir.join("bin").join("python3")
        }
    }

    /// Return the path to the Python binary inside the venv.
    pub fn venv_python(&self) -> PathBuf {
        if cfg!(target_os = "windows") {
            self.venv_dir.join("Scripts").join("python.exe")
        } else {
            self.venv_dir.join("bin").join("python3")
        }
    }

    /// Return the `requirements.txt` path.
    pub fn requirements_txt(&self) -> PathBuf {
        self.rumi_home.join("requirements.txt")
    }

    /// Return the persisted panel bootstrap secret path inside app data.
    pub fn panel_bootstrap_secret_path(&self) -> PathBuf {
        self.user_data_dir
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| self.user_data_dir.clone())
            .join(".rumi_panel_bootstrap_secret")
    }

    /// Return the directory where Viewer host broker files are stored.
    pub fn host_broker_dir(&self) -> PathBuf {
        self.user_data_dir.join("host_broker")
    }

    /// Return the path to the Viewer host broker connection file.
    pub fn host_broker_connection_path(&self) -> PathBuf {
        self.host_broker_dir().join("connection.json")
    }

    /// Return the path to the Viewer host broker audit log.
    pub fn host_broker_audit_log_path(&self) -> PathBuf {
        self.host_broker_dir().join("audit.jsonl")
    }

    /// Return the path where a bundled `uv` binary would live.
    ///
    /// Layout: `{app_dir}/bundled/uv` (Unix) or `{app_dir}/bundled/uv.exe` (Windows).
    pub fn bundled_uv_path(&self) -> PathBuf {
        self.app_dir.join("bundled").join(uv_binary_name())
    }

    /// Return the path where a development-checkout bundled `uv` binary lives.
    ///
    /// Layout: `{workspace_root}/rumi_ai_1_10/bundled/uv` (Unix) or
    /// `{workspace_root}/rumi_ai_1_10/bundled/uv.exe` (Windows).
    pub fn dev_bundled_uv_path(&self) -> Option<PathBuf> {
        self.dev_workspace_root.as_ref().map(|root| {
            root.join("rumi_ai_1_10")
                .join("bundled")
                .join(uv_binary_name())
        })
    }

    /// Resolve the best available `uv` binary path.
    ///
    /// Prefers the bundled copy shipped alongside the application.  Falls back
    /// to the downloaded copy at `self.uv_path`.
    pub fn resolved_uv_path(&self) -> PathBuf {
        let bundled = self.bundled_uv_path();
        if bundled.exists() {
            return bundled;
        }

        if let Some(dev_bundled) = self.dev_bundled_uv_path() {
            if dev_bundled.exists() {
                return dev_bundled;
            }
        }

        self.uv_path.clone()
    }

    pub fn is_dev_workspace(&self) -> bool {
        self.dev_workspace_root.is_some()
    }

    /// Resolve the best available `pack-shell` binary path.
    ///
    /// Checks the bundled copy at `{app_dir}/bundled/pack-shell` first,
    /// then falls back to the dev workspace build, then `PATH`.
    pub fn pack_shell_path(&self) -> Option<PathBuf> {
        let bundled = self.app_dir.join("bundled").join(pack_shell_binary_name());
        if bundled.exists() {
            return Some(bundled);
        }

        if let Some(ref root) = self.dev_workspace_root {
            let dev_release = root
                .join("pack-shell")
                .join("target")
                .join("release")
                .join(pack_shell_binary_name());
            if dev_release.exists() {
                return Some(dev_release);
            }
            let dev_debug = root
                .join("pack-shell")
                .join("target")
                .join("debug")
                .join(pack_shell_binary_name());
            if dev_debug.exists() {
                return Some(dev_debug);
            }
        }

        which::which(pack_shell_binary_name()).ok()
    }

    /// Return the path where the desktop API token is stored.
    ///
    /// Layout: `{app_data_dir}/.desktop_api_token`
    pub fn desktop_api_token_path(&self) -> PathBuf {
        self.user_data_dir
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| self.user_data_dir.clone())
            .join(".desktop_api_token")
    }

    /// Return the path to the defaultspack ecosystem.json.
    pub fn defaultspack_ecosystem_json(&self) -> PathBuf {
        for managed_root in self.defaultspack_managed_roots() {
            match resolve_defaultspack_current_pointer(&managed_root) {
                ManagedPointerResolution::Resolved(ecosystem_path) => {
                    log::info!(
                        "Using managed defaultspack ecosystem from {}",
                        ecosystem_path.display()
                    );
                    return ecosystem_path;
                }
                ManagedPointerResolution::Missing => {}
                ManagedPointerResolution::Invalid(reason) => {
                    let current_json = managed_root.join("current.json");
                    log::warn!(
                        "Ignoring defaultspack current pointer at {}: {}",
                        current_json.display(),
                        reason
                    );
                }
            }
        }

        self.app_dir
            .join("ecosystem")
            .join("defaultspack")
            .join("ecosystem.json")
    }

    fn defaultspack_managed_roots(&self) -> Vec<PathBuf> {
        let mut roots = Vec::with_capacity(2);
        for root in [
            self.rumi_home
                .join("user_data")
                .join("packs")
                .join("defaultspack"),
            self.user_data_dir.join("packs").join("defaultspack"),
        ] {
            if !roots.iter().any(|existing| existing == &root) {
                roots.push(root);
            }
        }
        roots
    }
}

enum ManagedPointerResolution {
    Resolved(PathBuf),
    Missing,
    Invalid(String),
}

fn resolve_defaultspack_current_pointer(managed_root: &Path) -> ManagedPointerResolution {
    let current_json = managed_root.join("current.json");
    if !current_json.exists() {
        return ManagedPointerResolution::Missing;
    }

    let raw = match std::fs::read_to_string(&current_json) {
        Ok(raw) => raw,
        Err(error) => {
            return ManagedPointerResolution::Invalid(format!("read failed: {error}"));
        }
    };
    let data = match serde_json::from_str::<serde_json::Value>(&raw) {
        Ok(data) => data,
        Err(error) => {
            return ManagedPointerResolution::Invalid(format!("invalid JSON: {error}"));
        }
    };

    if data.get("pack_id").and_then(|value| value.as_str()) != Some("defaultspack") {
        return ManagedPointerResolution::Invalid("pack_id must be 'defaultspack'".to_string());
    }

    let Some(rel) = data.get("path").and_then(|value| value.as_str()) else {
        return ManagedPointerResolution::Invalid("missing relative 'path'".to_string());
    };
    let rel_path = PathBuf::from(rel);
    if rel_path.is_absolute() {
        return ManagedPointerResolution::Invalid("path must be relative".to_string());
    }
    if rel_path
        .components()
        .any(|part| matches!(part, std::path::Component::ParentDir))
    {
        return ManagedPointerResolution::Invalid("path must not contain '..'".to_string());
    }

    let ecosystem = managed_root.join(rel_path).join("ecosystem.json");
    if !ecosystem.exists() {
        return ManagedPointerResolution::Invalid(format!(
            "ecosystem.json not found at {}",
            ecosystem.display()
        ));
    }

    ManagedPointerResolution::Resolved(ecosystem)
}

fn find_dev_workspace_root(resource_dir: &Path) -> Option<PathBuf> {
    for ancestor in resource_dir.ancestors() {
        let candidate = ancestor.join("rumi_ai_1_10");
        if candidate.join("app.py").exists() {
            return Some(ancestor.to_path_buf());
        }
    }
    None
}

/// Return the platform-appropriate file name for the `uv` binary.
fn uv_binary_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "uv.exe"
    } else {
        "uv"
    }
}

/// Return the platform-appropriate file name for the `pack-shell` binary.
fn pack_shell_binary_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "pack-shell.exe"
    } else {
        "pack-shell"
    }
}

/// Return the platform triple string used by python-build-standalone
/// and the `uv` release filenames.
pub fn platform_triple() -> &'static str {
    #[cfg(all(target_arch = "x86_64", target_os = "linux"))]
    {
        "x86_64-unknown-linux-gnu"
    }

    #[cfg(all(target_arch = "aarch64", target_os = "linux"))]
    {
        "aarch64-unknown-linux-gnu"
    }

    #[cfg(all(target_arch = "x86_64", target_os = "macos"))]
    {
        "x86_64-apple-darwin"
    }

    #[cfg(all(target_arch = "aarch64", target_os = "macos"))]
    {
        "aarch64-apple-darwin"
    }

    #[cfg(all(target_arch = "x86_64", target_os = "windows"))]
    {
        "x86_64-pc-windows-msvc"
    }

    #[cfg(all(target_arch = "aarch64", target_os = "windows"))]
    {
        "aarch64-pc-windows-msvc"
    }

    #[cfg(not(any(
        all(target_arch = "x86_64", target_os = "linux"),
        all(target_arch = "aarch64", target_os = "linux"),
        all(target_arch = "x86_64", target_os = "macos"),
        all(target_arch = "aarch64", target_os = "macos"),
        all(target_arch = "x86_64", target_os = "windows"),
        all(target_arch = "aarch64", target_os = "windows"),
    )))]
    {
        compile_error!("unsupported target platform")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn platform_triple_is_not_empty() {
        let triple = platform_triple();
        assert!(!triple.is_empty());
        assert!(triple.contains('-'));
    }

    #[test]
    fn detect_for_tauri_produces_valid_paths() {
        let resource = PathBuf::from("/tmp/test_resource");
        let appdata = PathBuf::from("/tmp/test_appdata");
        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        assert!(config.app_dir.to_string_lossy().contains("test_resource"));
        assert!(config.python_dir.to_string_lossy().contains("test_appdata"));
        assert_eq!(config.rumi_home, config.app_dir);
        assert!(!config.is_dev_workspace());
    }

    #[test]
    fn app_config_separates_app_dir_from_user_data_dir() {
        let config = AppConfig::detect_for_tauri(
            PathBuf::from("/tmp/resources"),
            PathBuf::from("/tmp/app-data"),
        )
        .unwrap();

        assert_eq!(config.app_dir, PathBuf::from("/tmp/resources/app"));
        assert_eq!(config.rumi_home, PathBuf::from("/tmp/resources/app"));
        assert_eq!(
            config.user_data_dir,
            PathBuf::from("/tmp/app-data/user_data")
        );
    }

    #[test]
    fn venv_python_path_is_reasonable() {
        let resource = PathBuf::from("/tmp/res");
        let appdata = PathBuf::from("/tmp/data");
        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        let vp = config.venv_python();
        assert!(vp.to_string_lossy().contains("venv"));
    }

    #[test]
    fn panel_bootstrap_secret_path_uses_appdata_root() {
        let resource = PathBuf::from("/tmp/res");
        let appdata = PathBuf::from("/tmp/data");
        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        assert_eq!(
            config.panel_bootstrap_secret_path(),
            PathBuf::from("/tmp/data/.rumi_panel_bootstrap_secret")
        );
    }

    #[test]
    fn detect_for_tauri_falls_back_to_repo_checkout_in_dev() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_config_{unique}"));
        let resource = root
            .join("rumi_viewer")
            .join("src-tauri")
            .join("target")
            .join("debug");
        let appdata = root.join("appdata");
        let app_py = root.join("rumi_ai_1_10").join("app.py");

        fs::create_dir_all(&resource).unwrap();
        fs::create_dir_all(app_py.parent().unwrap()).unwrap();
        fs::write(&app_py, "print('ok')\n").unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        assert_eq!(config.app_dir, root.join("rumi_ai_1_10"));
        assert!(config.is_dev_workspace());

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn resolved_uv_path_prefers_bundled_copy_in_app_dir() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_uv_app_bundle_{unique}"));
        let resource = root.join("resources");
        let app_dir = resource.join("app");
        let appdata = root.join("appdata");
        let bundled_uv = app_dir.join("bundled").join(uv_binary_name());

        fs::create_dir_all(bundled_uv.parent().unwrap()).unwrap();
        fs::write(&bundled_uv, b"uv").unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata.clone()).unwrap();
        assert_eq!(config.resolved_uv_path(), bundled_uv);
        assert_eq!(config.bundled_uv_path(), bundled_uv);

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn resolved_uv_path_prefers_dev_workspace_bundle_over_downloaded_uv() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_uv_dev_bundle_{unique}"));
        let resource = root
            .join("rumi_viewer")
            .join("src-tauri")
            .join("target")
            .join("debug");
        let appdata = root.join("appdata");
        let app_py = root.join("rumi_ai_1_10").join("app.py");
        let dev_bundled_uv = root
            .join("rumi_ai_1_10")
            .join("bundled")
            .join(uv_binary_name());

        fs::create_dir_all(&resource).unwrap();
        fs::create_dir_all(app_py.parent().unwrap()).unwrap();
        fs::create_dir_all(dev_bundled_uv.parent().unwrap()).unwrap();
        fs::write(&app_py, "print('ok')\n").unwrap();
        fs::write(&dev_bundled_uv, b"uv").unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata.clone()).unwrap();
        assert_eq!(
            config.dev_bundled_uv_path().as_deref(),
            Some(dev_bundled_uv.as_path())
        );
        assert_eq!(config.resolved_uv_path(), dev_bundled_uv);
        assert!(config.is_dev_workspace());

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn resolved_uv_path_falls_back_to_downloaded_uv_when_no_bundle_exists() {
        let resource = PathBuf::from("/tmp/res");
        let appdata = PathBuf::from("/tmp/data");
        let config = AppConfig::detect_for_tauri(resource, appdata.clone()).unwrap();

        assert_eq!(config.resolved_uv_path(), config.uv_path);
        assert_eq!(config.uv_path, appdata.join(uv_binary_name()));
    }

    #[test]
    fn defaultspack_ecosystem_prefers_managed_current_pointer() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_defaultspack_{unique}"));
        let resource = root.join("resources");
        let appdata = root.join("appdata");
        let managed = resource
            .join("app")
            .join("user_data")
            .join("packs")
            .join("defaultspack")
            .join("versions")
            .join("2.5.0");
        let legacy_managed = appdata
            .join("user_data")
            .join("packs")
            .join("defaultspack")
            .join("versions")
            .join("2.4.0");
        fs::create_dir_all(&managed).unwrap();
        fs::create_dir_all(&legacy_managed).unwrap();
        fs::write(managed.join("ecosystem.json"), "{}").unwrap();
        fs::write(legacy_managed.join("ecosystem.json"), "{}").unwrap();
        fs::write(
            resource
                .join("app")
                .join("user_data")
                .join("packs")
                .join("defaultspack")
                .join("current.json"),
            r#"{"schema":"rumi.pack_current.v1","pack_id":"defaultspack","version":"2.5.0","path":"versions/2.5.0"}"#,
        )
        .unwrap();
        fs::write(
            appdata
                .join("user_data")
                .join("packs")
                .join("defaultspack")
                .join("current.json"),
            r#"{"schema":"rumi.pack_current.v1","pack_id":"defaultspack","version":"2.4.0","path":"versions/2.4.0"}"#,
        )
        .unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();

        assert_eq!(
            config.defaultspack_ecosystem_json(),
            managed.join("ecosystem.json")
        );
        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn defaultspack_ecosystem_falls_back_to_appdata_current_pointer_for_migration() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_defaultspack_appdata_{unique}"));
        let resource = root.join("resources");
        let appdata = root.join("appdata");
        let managed = appdata
            .join("user_data")
            .join("packs")
            .join("defaultspack")
            .join("versions")
            .join("2.5.0");
        fs::create_dir_all(&managed).unwrap();
        fs::write(managed.join("ecosystem.json"), "{}").unwrap();
        fs::write(
            appdata
                .join("user_data")
                .join("packs")
                .join("defaultspack")
                .join("current.json"),
            r#"{"schema":"rumi.pack_current.v1","pack_id":"defaultspack","version":"2.5.0","path":"versions/2.5.0"}"#,
        )
        .unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();

        assert_eq!(
            config.defaultspack_ecosystem_json(),
            managed.join("ecosystem.json")
        );
        fs::remove_dir_all(&root).ok();
    }
}
