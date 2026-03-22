//! Kernel process lifecycle management.
//!
//! Responsibilities:
//! - Start the Python Kernel (`python -m app`) inside the venv.
//! - Stop it gracefully (SIGTERM -> timeout -> SIGKILL on Unix, kill on Windows).
//! - Detect exit-code 42 to signal "please restart me".
//! - Auto-restart on unexpected exit (max 3 times).

use std::fs;
use std::process::{Child, Command, Stdio};

use anyhow::{bail, Context, Result};
use log::{error, info, warn};

use crate::config::AppConfig;

/// Special exit code: the Kernel requests a restart.
const RESTART_EXIT_CODE: i32 = 42;

/// Maximum consecutive non-42 restarts before giving up.
const MAX_AUTO_RESTARTS: u32 = 3;

/// Seconds to wait after SIGTERM before sending SIGKILL.
const KILL_TIMEOUT_SECS: u64 = 5;

/// Manages a single Kernel child process.
pub struct KernelManager {
    child: Option<Child>,
    config: AppConfig,
    /// Stores the exit code from the most recent child exit.
    last_exit_code: Option<i32>,
    /// Counter for consecutive non-42 restarts.
    restart_count: u32,
}

impl KernelManager {
    pub fn new(config: &AppConfig) -> Self {
        Self {
            child: None,
            config: config.clone(),
            last_exit_code: None,
            restart_count: 0,
        }
    }

    /// Start the Kernel process.
    ///
    /// Runs `{venv}/bin/python -m app` with cwd = `rumi_home`.
    /// Stdout and stderr are redirected to `{log_dir}/kernel.log`.
    pub fn start(&mut self) -> Result<()> {
        if self.is_running() {
            info!("Kernel already running, skipping start");
            return Ok(());
        }

        let venv_python = self.config.venv_python();

        if !venv_python.exists() {
            bail!(
                "venv Python not found at {} -- run environment setup first",
                venv_python.display()
            );
        }
        if !self.config.rumi_home.exists() {
            bail!(
                "Kernel directory not found: {}",
                self.config.rumi_home.display()
            );
        }

        fs::create_dir_all(&self.config.log_dir)?;
        let log_file = fs::File::create(self.config.log_dir.join("kernel.log"))
            .context("failed to create kernel.log")?;
        let log_stderr = log_file
            .try_clone()
            .context("failed to clone log file handle")?;

        info!(
            "Starting Kernel: {} -m app (cwd={})",
            venv_python.display(),
            self.config.rumi_home.display()
        );

        let child = Command::new(&venv_python)
            .args(["-m", "app"])
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

        info!("Stopping Kernel (pid {}) ...", child.id());

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

    /// Stop then start. Resets the restart counter.
    pub fn restart(&mut self) -> Result<()> {
        self.stop()?;
        self.restart_count = 0;
        self.start()
    }

    /// Consume the last exit status and decide whether to auto-restart.
    ///
    /// Returns `true` if the caller should call `start()` again.
    pub fn wait_and_handle_restart(&mut self) -> Result<bool> {
        if let Some(child) = self.child.as_mut() {
            let status = child.wait().context("failed to wait on Kernel")?;
            let code = status.code().unwrap_or(-1);
            self.last_exit_code = Some(code);
            self.child = None;
        }

        match self.last_exit_code.take() {
            Some(RESTART_EXIT_CODE) => {
                info!("Kernel exited with code 42 -- restart requested");
                self.restart_count = 0;
                Ok(true)
            }
            Some(0) => {
                info!("Kernel exited normally (code 0)");
                Ok(false)
            }
            Some(code) => {
                self.restart_count += 1;
                if self.restart_count <= MAX_AUTO_RESTARTS {
                    warn!(
                        "Kernel exited with code {code} -- auto-restart {}/{}",
                        self.restart_count, MAX_AUTO_RESTARTS
                    );
                    Ok(true)
                } else {
                    error!(
                        "Kernel exited with code {code} -- max restarts ({}) exceeded, giving up",
                        MAX_AUTO_RESTARTS
                    );
                    Ok(false)
                }
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
        assert!(!km.is_running());
    }

    #[test]
    fn stop_without_start_is_ok() {
        let config = AppConfig::detect().unwrap();
        let mut km = KernelManager::new(&config);
        assert!(km.stop().is_ok());
    }

    #[test]
    fn wait_and_handle_restart_no_child() {
        let config = AppConfig::detect().unwrap();
        let mut km = KernelManager::new(&config);
        let result = km.wait_and_handle_restart().unwrap();
        assert!(!result);
    }
}
