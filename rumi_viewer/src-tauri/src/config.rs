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

    /// Return the path where a bundled `uv` binary would live.
    ///
    /// Layout: `{app_dir}/bundled/uv` (Unix) or `{app_dir}/bundled/uv.exe` (Windows).
    pub fn bundled_uv_path(&self) -> PathBuf {
        self.app_dir.join("bundled").join(uv_binary_name())
    }

    /// Resolve the best available `uv` binary path.
    ///
    /// Prefers the bundled copy shipped alongside the application.  Falls back
    /// to the downloaded copy at `self.uv_path`.
    pub fn resolved_uv_path(&self) -> PathBuf {
        let bundled = self.bundled_uv_path();
        if bundled.exists() {
            bundled
        } else {
            self.uv_path.clone()
        }
    }

    pub fn is_dev_workspace(&self) -> bool {
        self.dev_workspace_root.is_some()
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

/// Return the platform-appropriate file name for the `uv` binary.
fn uv_binary_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "uv.exe"
    } else {
        "uv"
    }
}

/// Return the platform triple string used by python-build-standalone
/// and the `uv` release filenames.
pub fn platform_triple() -> &'static str {
    #[cfg(all(target_arch = "x86_64", target_os = "linux"))]
    { "x86_64-unknown-linux-gnu" }

    #[cfg(all(target_arch = "aarch64", target_os = "linux"))]
    { "aarch64-unknown-linux-gnu" }

    #[cfg(all(target_arch = "x86_64", target_os = "macos"))]
    { "x86_64-apple-darwin" }

    #[cfg(all(target_arch = "aarch64", target_os = "macos"))]
    { "aarch64-apple-darwin" }

    #[cfg(all(target_arch = "x86_64", target_os = "windows"))]
    { "x86_64-pc-windows-msvc" }

    #[cfg(all(target_arch = "aarch64", target_os = "windows"))]
    { "aarch64-pc-windows-msvc" }

    #[cfg(not(any(
        all(target_arch = "x86_64", target_os = "linux"),
        all(target_arch = "aarch64", target_os = "linux"),
        all(target_arch = "x86_64", target_os = "macos"),
        all(target_arch = "aarch64", target_os = "macos"),
        all(target_arch = "x86_64", target_os = "windows"),
        all(target_arch = "aarch64", target_os = "windows"),
    )))]
    { compile_error!("unsupported target platform") }
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
    fn venv_python_path_is_reasonable() {
        let resource = PathBuf::from("/tmp/res");
        let appdata = PathBuf::from("/tmp/data");
        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        let vp = config.venv_python();
        assert!(vp.to_string_lossy().contains("venv"));
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
        let resource = root.join("rumi_viewer").join("src-tauri").join("target").join("debug");
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
}
