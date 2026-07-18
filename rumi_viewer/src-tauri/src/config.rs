//! Path resolution and application configuration for Tauri.
//!
//! All paths are derived from Tauri's `resource_dir` and `app_data_dir`
//! so that the application works correctly when bundled.

use crate::process_utils;

use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};
use std::process::Stdio;

const PACK_SHELL_PATH_ENV: &str = "RUMI_PACK_SHELL_PATH";
const UV_PATH_ENV: &str = "RUMI_UV_PATH";

/// Central configuration resolved from Tauri path APIs.
#[derive(Debug, Clone)]
pub struct AppConfig {
    /// `{resource_dir}/app` — bundled rumi_ai_1_10 contents (= kernel root).
    pub app_dir: PathBuf,
    /// Same as `app_dir` — the Kernel's working directory.
    pub rumi_home: PathBuf,
    /// `{app_data_dir}/python` — PBS standalone Python.
    pub python_dir: PathBuf,
    /// Legacy app-data `uv` path retained for diagnostics and migration state.
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
        let staged_app_dir = resource_dir.join("app");
        let detected_workspace_root = find_dev_workspace_root(&resource_dir);
        let prefer_dev_runtime =
            cfg!(debug_assertions) && is_cargo_debug_resource_dir(&resource_dir);
        let dev_workspace_root = if prefer_dev_runtime {
            detected_workspace_root
        } else if staged_app_dir.exists() {
            None
        } else {
            detected_workspace_root
        };

        let mut app_dir = staged_app_dir;
        if let Some(workspace_root) = &dev_workspace_root {
            let candidate = workspace_root.join("rumi_ai_1_10");
            if candidate.join("app.py").exists() {
                app_dir = candidate;
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

    /// Return the owner-only directory containing consumed approval markers.
    pub fn host_broker_approval_replay_dir(&self) -> PathBuf {
        self.host_broker_dir().join("consumed_approvals")
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

    /// Resolve a trusted `uv` binary path.
    ///
    /// Runtime downloads are intentionally not part of this trust boundary. The
    /// viewer may use a bundled `uv`, a development-checkout bundle, an explicit
    /// `RUMI_UV_PATH`, or a user-managed `uv` on PATH.
    pub fn trusted_uv_path(&self) -> Option<PathBuf> {
        let bundled = self.bundled_uv_path();
        if bundled.exists() {
            return Some(bundled);
        }

        if let Some(dev_bundled) = self.dev_bundled_uv_path() {
            if dev_bundled.exists() {
                return Some(dev_bundled);
            }
        }

        if let Some(configured) = configured_uv_path() {
            if configured.is_file() {
                return Some(configured);
            }
        }

        which::which(uv_binary_name()).ok()
    }

    /// Resolve the best available `uv` binary path for diagnostics.
    pub fn resolved_uv_path(&self) -> PathBuf {
        self.trusted_uv_path()
            .unwrap_or_else(|| self.uv_path.clone())
    }

    pub fn is_dev_workspace(&self) -> bool {
        self.dev_workspace_root.is_some()
    }

    /// Resolve the best available `pack-shell` binary path.
    ///
    /// Checks `RUMI_PACK_SHELL_PATH` first, then the bundled copy at
    /// `{app_dir}/bundled/pack-shell`, then the dev workspace build, then
    /// `PATH`.
    pub fn pack_shell_path(&self) -> Option<PathBuf> {
        if let Some(configured) = configured_pack_shell_path() {
            if configured.is_file() {
                return Some(configured);
            }
        }

        if let Some(bundled) = self.bundled_pack_shell_path() {
            return Some(bundled);
        }

        if let Some(ref root) = self.dev_workspace_root {
            if let Some(dev_pack_shell) = dev_pack_shell_path(root) {
                return Some(dev_pack_shell);
            }
        }

        which::which(pack_shell_binary_name()).ok()
    }

    /// Resolve `pack-shell`, building the dev checkout copy on first use.
    pub fn ensure_pack_shell_path(&self) -> Result<PathBuf> {
        self.ensure_pack_shell_path_with(build_dev_pack_shell)
    }

    fn ensure_pack_shell_path_with<F>(&self, mut build_pack_shell: F) -> Result<PathBuf>
    where
        F: FnMut(&Path) -> Result<()>,
    {
        if let Some(configured) = configured_pack_shell_path() {
            if configured.is_file() {
                return Ok(configured);
            }
            bail!(
                "{PACK_SHELL_PATH_ENV} points to a missing pack-shell binary: {}",
                configured.display()
            );
        }

        if let Some(ref root) = self.dev_workspace_root {
            if let Some(dev_pack_shell) = dev_pack_shell_path(root) {
                return Ok(dev_pack_shell);
            }

            let manifest = root.join("pack-shell").join("Cargo.toml");
            if manifest.is_file() {
                log::info!(
                    "pack-shell binary not found; building dev pack-shell from {}",
                    manifest.display()
                );
                build_pack_shell(&manifest).with_context(|| {
                    format!("failed to build pack-shell from {}", manifest.display())
                })?;

                return dev_pack_shell_path(root).with_context(|| {
                    format!(
                        "pack-shell build completed but {} was not created",
                        dev_pack_shell_binary_path(root, "debug").display()
                    )
                });
            }
        }

        if let Some(bundled) = self.bundled_pack_shell_path() {
            return Ok(bundled);
        }

        if let Ok(found) = which::which(pack_shell_binary_name()) {
            return Ok(found);
        }

        bail!(
            "pack-shell binary not found. Set {PACK_SHELL_PATH_ENV}, add pack-shell to PATH, or build it with `cargo build --manifest-path pack-shell/Cargo.toml`."
        );
    }

    fn bundled_pack_shell_path(&self) -> Option<PathBuf> {
        let bundled = self.app_dir.join("bundled").join(pack_shell_binary_name());
        if bundled.is_file() {
            Some(bundled)
        } else {
            None
        }
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

    /// Return the canonical bundled defaultspack ecosystem.json.
    ///
    /// The viewer launches defaultspack with the local Pack API token, so the
    /// host-side launch path must not be redirected by user-writable managed
    /// pack pointers. Built-in defaultspack is trusted only from the shipped
    /// application bundle (or the repo copy while running a dev workspace).
    pub fn defaultspack_ecosystem_json(&self) -> PathBuf {
        let bundled = self.bundled_defaultspack_ecosystem_json();
        if self.is_dev_workspace() && bundled.exists() {
            log::info!(
                "Using repo defaultspack ecosystem during viewer dev startup from {}",
                bundled.display()
            );
        }

        bundled
    }

    fn bundled_defaultspack_ecosystem_json(&self) -> PathBuf {
        self.app_dir
            .join("ecosystem")
            .join("defaultspack")
            .join("ecosystem.json")
    }
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

fn is_cargo_debug_resource_dir(resource_dir: &Path) -> bool {
    let mut components = resource_dir.components().rev();
    matches!(
        (
            components
                .next()
                .and_then(|component| component.as_os_str().to_str()),
            components
                .next()
                .and_then(|component| component.as_os_str().to_str()),
        ),
        (Some("debug"), Some("target"))
    )
}

fn configured_uv_path() -> Option<PathBuf> {
    std::env::var_os(UV_PATH_ENV)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

fn configured_pack_shell_path() -> Option<PathBuf> {
    std::env::var_os(PACK_SHELL_PATH_ENV)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

fn dev_pack_shell_binary_path(root: &Path, profile: &str) -> PathBuf {
    root.join("pack-shell")
        .join("target")
        .join(profile)
        .join(pack_shell_binary_name())
}

fn dev_pack_shell_path(root: &Path) -> Option<PathBuf> {
    for profile in ["release", "debug"] {
        let candidate = dev_pack_shell_binary_path(root, profile);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

fn build_dev_pack_shell(manifest: &Path) -> Result<()> {
    let output = process_utils::command("cargo")
        .arg("build")
        .arg("--manifest-path")
        .arg(manifest)
        .stdin(Stdio::null())
        .output()
        .context("failed to run cargo build for pack-shell")?;

    if output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        if !stderr.trim().is_empty() {
            log::info!("pack-shell cargo build output: {}", stderr.trim());
        }
        return Ok(());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    bail!(
        "cargo build for pack-shell failed with status {}\nstdout:\n{}\nstderr:\n{}",
        output.status,
        stdout.trim(),
        stderr.trim()
    );
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
    fn detect_for_tauri_does_not_trust_ancestors_when_bundled_app_exists() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_config_staged_{unique}"));
        let resource = root.join("resources");
        let staged_app_py = resource.join("app").join("app.py");
        let repo_app_py = root.join("rumi_ai_1_10").join("app.py");

        fs::create_dir_all(staged_app_py.parent().unwrap()).unwrap();
        fs::create_dir_all(repo_app_py.parent().unwrap()).unwrap();
        fs::write(&staged_app_py, "print('staged')\n").unwrap();
        fs::write(&repo_app_py, "print('repo')\n").unwrap();

        let config = AppConfig::detect_for_tauri(resource.clone(), root.join("appdata")).unwrap();

        assert_eq!(config.app_dir, resource.join("app"));
        assert_eq!(config.dev_workspace_root, None);
        assert!(!config.is_dev_workspace());

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn detect_for_tauri_prefers_repo_checkout_over_stale_debug_bundle() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_config_debug_staged_{unique}"));
        let resource = root
            .join("rumi_viewer")
            .join("src-tauri")
            .join("target")
            .join("debug");
        let staged_app_py = resource.join("app").join("app.py");
        let repo_app_py = root.join("rumi_ai_1_10").join("app.py");

        fs::create_dir_all(staged_app_py.parent().unwrap()).unwrap();
        fs::create_dir_all(repo_app_py.parent().unwrap()).unwrap();
        fs::write(&staged_app_py, "print('staged')\n").unwrap();
        fs::write(&repo_app_py, "print('repo')\n").unwrap();

        let config = AppConfig::detect_for_tauri(resource.clone(), root.join("appdata")).unwrap();

        assert_eq!(config.app_dir, root.join("rumi_ai_1_10"));
        assert_eq!(config.dev_workspace_root, Some(root.clone()));
        assert!(config.is_dev_workspace());

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn trusted_uv_path_prefers_bundled_copy_in_app_dir() {
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
        assert_eq!(
            config.trusted_uv_path().as_deref(),
            Some(bundled_uv.as_path())
        );
        assert_eq!(config.bundled_uv_path(), bundled_uv);

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn trusted_uv_path_prefers_dev_workspace_bundle_over_appdata_uv() {
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
        assert_eq!(
            config.trusted_uv_path().as_deref(),
            Some(dev_bundled_uv.as_path())
        );
        assert!(config.is_dev_workspace());

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn trusted_uv_path_ignores_appdata_uv_when_no_trusted_source_exists() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_uv_appdata_ignored_{unique}"));
        let resource = root.join("resources");
        let appdata = root.join("appdata");

        fs::create_dir_all(&appdata).unwrap();
        fs::write(appdata.join(uv_binary_name()), b"uv").unwrap();

        let old_path = std::env::var_os("PATH");
        let old_uv_path = std::env::var_os(UV_PATH_ENV);
        std::env::set_var("PATH", "");
        std::env::remove_var(UV_PATH_ENV);
        let config = AppConfig::detect_for_tauri(resource, appdata.clone()).unwrap();

        assert_eq!(config.trusted_uv_path(), None);
        assert_eq!(config.resolved_uv_path(), config.uv_path);
        assert_eq!(config.uv_path, appdata.join(uv_binary_name()));

        if let Some(path) = old_path {
            std::env::set_var("PATH", path);
        } else {
            std::env::remove_var("PATH");
        }
        if let Some(path) = old_uv_path {
            std::env::set_var(UV_PATH_ENV, path);
        } else {
            std::env::remove_var(UV_PATH_ENV);
        }
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn pack_shell_path_prefers_dev_build_when_present() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_pack_shell_{unique}"));
        let resource = root
            .join("rumi_viewer")
            .join("src-tauri")
            .join("target")
            .join("debug");
        let appdata = root.join("appdata");
        let app_py = root.join("rumi_ai_1_10").join("app.py");
        let pack_shell = dev_pack_shell_binary_path(&root, "debug");

        fs::create_dir_all(&resource).unwrap();
        fs::create_dir_all(app_py.parent().unwrap()).unwrap();
        fs::create_dir_all(pack_shell.parent().unwrap()).unwrap();
        fs::write(&app_py, "print('ok')\n").unwrap();
        fs::write(&pack_shell, b"pack-shell").unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();

        assert_eq!(config.pack_shell_path(), Some(pack_shell.clone()));
        assert_eq!(config.ensure_pack_shell_path().unwrap(), pack_shell);

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn ensure_pack_shell_path_builds_dev_binary_when_missing() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_pack_shell_build_{unique}"));
        let resource = root
            .join("rumi_viewer")
            .join("src-tauri")
            .join("target")
            .join("debug");
        let appdata = root.join("appdata");
        let app_py = root.join("rumi_ai_1_10").join("app.py");
        let manifest = root.join("pack-shell").join("Cargo.toml");
        let pack_shell = dev_pack_shell_binary_path(&root, "debug");

        fs::create_dir_all(&resource).unwrap();
        fs::create_dir_all(app_py.parent().unwrap()).unwrap();
        fs::create_dir_all(manifest.parent().unwrap()).unwrap();
        fs::write(&app_py, "print('ok')\n").unwrap();
        fs::write(&manifest, "[package]\nname = \"pack-shell\"\n").unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        let built = config
            .ensure_pack_shell_path_with(|manifest_path| {
                assert_eq!(manifest_path, manifest.as_path());
                fs::create_dir_all(pack_shell.parent().unwrap()).unwrap();
                fs::write(&pack_shell, b"pack-shell").unwrap();
                Ok(())
            })
            .unwrap();

        assert_eq!(built, pack_shell);

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn ensure_pack_shell_path_uses_staged_bundle_without_building_ancestor_workspace() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_pack_shell_staged_{unique}"));
        let resource = root.join("resources");
        let appdata = root.join("appdata");
        let app_py = root.join("rumi_ai_1_10").join("app.py");
        let manifest = root.join("pack-shell").join("Cargo.toml");
        let staged_pack_shell = resource
            .join("app")
            .join("bundled")
            .join(pack_shell_binary_name());

        fs::create_dir_all(&resource).unwrap();
        fs::create_dir_all(app_py.parent().unwrap()).unwrap();
        fs::create_dir_all(manifest.parent().unwrap()).unwrap();
        fs::create_dir_all(staged_pack_shell.parent().unwrap()).unwrap();
        fs::write(&app_py, "print('ok')\n").unwrap();
        fs::write(&manifest, "[package]\nname = \"pack-shell\"\n").unwrap();
        fs::write(&staged_pack_shell, b"staged-pack-shell").unwrap();

        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        let resolved = config
            .ensure_pack_shell_path_with(|manifest_path| {
                panic!(
                    "unexpected build of ancestor manifest {}",
                    manifest_path.display()
                );
            })
            .unwrap();

        assert_eq!(resolved, staged_pack_shell);

        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn defaultspack_ecosystem_ignores_managed_current_pointer() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_defaultspack_{unique}"));
        let resource = root.join("resources");
        let appdata = root.join("appdata");
        let bundled = resource.join("app").join("ecosystem").join("defaultspack");
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
        fs::create_dir_all(&bundled).unwrap();
        fs::create_dir_all(&managed).unwrap();
        fs::create_dir_all(&legacy_managed).unwrap();
        fs::write(
            bundled.join("ecosystem.json"),
            r#"{"pack_id":"defaultspack"}"#,
        )
        .unwrap();
        fs::write(
            managed.join("ecosystem.json"),
            r#"{"pack_id":"defaultspack","desktop_app":{"command":"evil"}}"#,
        )
        .unwrap();
        fs::write(
            legacy_managed.join("ecosystem.json"),
            r#"{"pack_id":"defaultspack","desktop_app":{"command":"legacy-evil"}}"#,
        )
        .unwrap();
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
            bundled.join("ecosystem.json")
        );
        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn defaultspack_ecosystem_ignores_appdata_current_pointer_for_migration() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_defaultspack_appdata_{unique}"));
        let resource = root.join("resources");
        let appdata = root.join("appdata");
        let bundled = resource.join("app").join("ecosystem").join("defaultspack");
        let managed = appdata
            .join("user_data")
            .join("packs")
            .join("defaultspack")
            .join("versions")
            .join("2.5.0");
        fs::create_dir_all(&bundled).unwrap();
        fs::create_dir_all(&managed).unwrap();
        fs::write(
            bundled.join("ecosystem.json"),
            r#"{"pack_id":"defaultspack"}"#,
        )
        .unwrap();
        fs::write(
            managed.join("ecosystem.json"),
            r#"{"pack_id":"defaultspack","desktop_app":{"command":"evil"}}"#,
        )
        .unwrap();
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
            bundled.join("ecosystem.json")
        );
        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn defaultspack_ecosystem_prefers_repo_pack_in_dev_workspace() {
        use std::fs;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_defaultspack_dev_{unique}"));
        let resource = root.join("rumi_viewer").join("src-tauri").join("resources");
        let appdata = root.join("appdata");
        let repo_defaultspack = root
            .join("rumi_ai_1_10")
            .join("ecosystem")
            .join("defaultspack");
        let managed = appdata
            .join("user_data")
            .join("packs")
            .join("defaultspack")
            .join("versions")
            .join("2.5.0");

        fs::create_dir_all(&repo_defaultspack).unwrap();
        fs::create_dir_all(&managed).unwrap();
        fs::write(root.join("rumi_ai_1_10").join("app.py"), "print('ok')\n").unwrap();
        fs::write(
            repo_defaultspack.join("ecosystem.json"),
            "{\"source\":\"repo\"}",
        )
        .unwrap();
        fs::write(managed.join("ecosystem.json"), "{\"source\":\"managed\"}").unwrap();
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
            repo_defaultspack.join("ecosystem.json")
        );
        fs::remove_dir_all(&root).ok();
    }
}
