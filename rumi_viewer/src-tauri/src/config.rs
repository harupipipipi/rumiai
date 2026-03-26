//! Path resolution and application configuration for Tauri.
//!
//! All paths are derived from Tauri's `resource_dir` and `app_data_dir`
//! so that the application works correctly when bundled.

use anyhow::Result;
use std::path::PathBuf;

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
        let app_dir = resource_dir.join("app");
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
    }

    #[test]
    fn venv_python_path_is_reasonable() {
        let resource = PathBuf::from("/tmp/res");
        let appdata = PathBuf::from("/tmp/data");
        let config = AppConfig::detect_for_tauri(resource, appdata).unwrap();
        let vp = config.venv_python();
        assert!(vp.to_string_lossy().contains("venv"));
    }
}
