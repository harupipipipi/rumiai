//! Kernel process lifecycle management.
//!
//! Responsibilities:
//! - Start the Python Kernel (`app.py`) inside the venv.
//! - Stop it gracefully (SIGTERM → timeout → SIGKILL on Unix, kill on Windows).
//! - Detect exit-code 42 to signal "please restart me".

use std::fs;
use std::process::{Child, Command, Stdio};

use anyhow::{bail, Context, Result};
use log::{error, info, warn};

use crate::config::AppConfig;

/// Special exit code: the Kernel requests a restart.
const RESTART_EXIT_CODE: i32 = 42;

/// Seconds to wait after SIGTERM before sending SIGKILL.
const KILL_TIMEOUT_SECS: u64 = 5;

/// Manages a single Kernel child process.
pub struct KernelManager {
    child: Option<Child>,
    config: AppConfig,
    /// Stores the exit code from the most recent child exit so that the
    /// caller can retrieve it even after `is_running()` has consumed the
    /// status.
    last_exit_code: Option<i32>,
}

impl KernelManager {
    pub fn new(config: &AppConfig) -> Self {
        Self {
            child: None,
            config: config.clone(),
            last_exit_code: None,
        }
    }

    /// Start the Kernel process.
    ///
    /// Stdout and stderr are redirected to `{log_dir}/kernel.log`.
    pub fn start(&mut self) -> Result<()> {
        if self.is_running() {
            info!("Kernel already running, skipping start");
            return Ok(());
        }

        let venv_python = self.config.venv_python();
        let entry = self.config.rumi_home.join(&self.config.kernel_entry);

        if !venv_python.exists() {
            bail!(
                "venv Python not found at {} — run environment setup first",
                venv_python.display()
            );
        }
        if !entry.exists() {
            bail!("Kernel entry-point not found: {}", entry.display());
        }

        fs::create_dir_all(&self.config.log_dir)?;
        let log_file = fs::File::create(self.config.log_dir.join("kernel.log"))
            .context("failed to create kernel.log")?;
        let log_stderr = log_file
            .try_clone()
            .context("failed to clone log file handle")?;

        info!(
            "Starting Kernel: {} {}",
            venv_python.display(),
            entry.display()
        );

        let child = Command::new(&venv_python)
            .arg(&entry)
            .current_dir(&self.config.rumi_home)
            .stdout(Stdio::from(log_file))
            .stderr(Stdio::from(log_stderr))
            .spawn()
            .context("failed to spawn Kernel process")?;

        info!("Kernel started (pid {})", child.id());
        self.child = Some(child);
        self.last_exit_code = None;
        Ok(())
    }

    /// Stop the Kernel process.
    pub fn stop(&mut self) -> Result<()> {
        let child = match self.child.as_mut() {
            Some(c) => c,
            None => {
                info!("No Kernel process to stop");
                return Ok(());
            }
        };

        info!("Stopping Kernel (pid {}) …", child.id());

        #[cfg(unix)]
        {
            Self::unix_stop(child)?;
        }

        #[cfg(not(unix))]
        {
            child.kill().ok();
            child.wait().ok();
        }

        self.child = None;
        info!("Kernel stopped");
        Ok(())
    }

    /// Stop then start.
    pub fn restart(&mut self) -> Result<()> {
        self.stop()?;
        self.start()
    }

    /// Consume the last exit status.
    ///
    /// If the child is still present, this blocks briefly to collect the
    /// status.  Returns `true` if exit code was 42 (restart requested).
    pub fn wait_and_handle_restart(&mut self) -> Result<bool> {
        // If we still hold the child handle, wait on it.
        if let Some(child) = self.child.as_mut() {
            let status = child.wait().context("failed to wait on Kernel")?;
            let code = status.code().unwrap_or(-1);
            self.last_exit_code = Some(code);
            self.child = None;
        }

        // Check the stored exit code.
        match self.last_exit_code.take() {
            Some(RESTART_EXIT_CODE) => {
                info!("Kernel exited with code 42 — restart requested");
                Ok(true)
            }
            Some(0) => {
                info!("Kernel exited normally (code 0)");
                Ok(false)
            }
            Some(code) => {
                warn!("Kernel exited with code {code}");
                Ok(false)
            }
            None => Ok(false),
        }
    }

    /// Returns `true` if the child process exists and has not yet exited.
    pub fn is_running(&mut self) -> bool {
        match self.child.as_mut() {
            Some(child) => match child.try_wait() {
                Ok(Some(status)) => {
                    self.last_exit_code = status.code();
                    self.child = None;
                    false
                }
                Ok(None) => true,
                Err(e) => {
                    error!("try_wait error: {e}");
                    false
                }
            },
            None => false,
        }
    }

    #[cfg(unix)]
    fn unix_stop(child: &mut Child) -> Result<()> {
        use std::thread;
        use std::time::Duration;

        let pid = child.id() as i32;
        let _ = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status();

        for _ in 0..KILL_TIMEOUT_SECS {
            thread::sleep(Duration::from_secs(1));
            if let Ok(Some(_)) = child.try_wait() {
                return Ok(());
            }
        }

        warn!("Kernel did not exit after SIGTERM, sending SIGKILL");
        child.kill().ok();
        child.wait().ok();
        Ok(())
    }
}

impl Drop for KernelManager {
    fn drop(&mut self) {
        if self.is_running() {
            if let Err(e) = self.stop() {
                error!("Failed to stop Kernel during drop: {e}");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn is_running_default_false() {
        let config = AppConfig::detect().unwrap();
        let mut km = KernelManager::new(&config);
        assert!(!km.is_running(), "should not be running by default");
    }

    #[test]
    fn stop_without_start_is_ok() {
        let config = AppConfig::detect().unwrap();
        let mut km = KernelManager::new(&config);
        assert!(km.stop().is_ok(), "stop with no child should succeed");
    }

    #[test]
    fn wait_and_handle_restart_no_child() {
        let config = AppConfig::detect().unwrap();
        let mut km = KernelManager::new(&config);
        let result = km.wait_and_handle_restart().unwrap();
        assert!(!result, "no child should return false");
    }
}
