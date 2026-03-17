//! Path resolution and application configuration.
//!
//! All paths are derived from the location of the launcher binary so that
//! the application is fully relocatable.

use anyhow::{Context, Result};
use std::path::PathBuf;

/// Central configuration resolved from the launcher binary location.
#[derive(Debug, Clone)]
pub struct AppConfig {
    /// Directory that contains the launcher binary (= distribution root).
    pub app_dir: PathBuf,
    /// `{app_dir}/rumi_ai_1_10` — Python source tree.
    pub rumi_home: PathBuf,
    /// `{app_dir}/python` — PBS standalone Python.
    pub python_dir: PathBuf,
    /// Path to the `uv` binary.
    pub uv_path: PathBuf,
    /// `{app_dir}/.venv` — Python virtual-environment.
    pub venv_dir: PathBuf,
    /// `{app_dir}/user_data` — persistent user data.
    pub user_data_dir: PathBuf,
    /// `{app_dir}/logs` — log files.
    pub log_dir: PathBuf,
    /// Kernel HTTP port (default 8765).
    pub kernel_port: u16,
    /// Python entry-point relative to `rumi_home` (default `app.py`).
    pub kernel_entry: String,
}

impl AppConfig {
    /// Detect configuration from the running executable's location.
    ///
    /// The layout mirrors the distribution structure:
    /// ```text
    /// {app_dir}/
    /// ├── rumi_launcher(.exe)
    /// ├── rumi_ai_1_10/
    /// ├── python/
    /// ├── uv(.exe)
    /// ├── .venv/
    /// ├── user_data/
    /// └── logs/
    /// ```
    pub fn detect() -> Result<Self> {
        let exe = std::env::current_exe().context("failed to locate current executable")?;
        let app_dir = exe
            .parent()
            .context("executable has no parent directory")?
            .to_path_buf();

        let rumi_home = app_dir.join("rumi_ai_1_10");
        let python_dir = app_dir.join("python");
        let uv_path = if cfg!(target_os = "windows") {
            app_dir.join("uv.exe")
        } else {
            app_dir.join("uv")
        };
        let venv_dir = app_dir.join(".venv");
        let user_data_dir = app_dir.join("user_data");
        let log_dir = app_dir.join("logs");

        Ok(Self {
            app_dir,
            rumi_home,
            python_dir,
            uv_path,
            venv_dir,
            user_data_dir,
            log_dir,
            kernel_port: 8765,
            kernel_entry: "app.py".to_string(),
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
}

/// Return the platform triple string used by python-build-standalone
/// and the `uv` release filenames.
///
/// Examples: `"x86_64-unknown-linux-gnu"`, `"aarch64-apple-darwin"`,
/// `"x86_64-pc-windows-msvc"`.
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

    #[test]
    fn platform_triple_is_not_empty() {
        let triple = platform_triple();
        assert!(!triple.is_empty(), "platform_triple() must not be empty");
        assert!(
            triple.contains('-'),
            "platform_triple() should contain hyphens"
        );
    }

    #[test]
    fn detect_does_not_panic() {
        // In test environments rumi_ai_1_10 may not exist next to the
        // test binary, but detect() should still succeed (it only
        // builds paths, it does not check existence).
        let config = AppConfig::detect();
        assert!(config.is_ok(), "AppConfig::detect() should not fail");
    }

    #[test]
    fn venv_python_path_is_reasonable() {
        let config = AppConfig::detect().unwrap();
        let vp = config.venv_python();
        assert!(
            vp.to_string_lossy().contains(".venv"),
            "venv_python path should contain .venv"
        );
    }
}
