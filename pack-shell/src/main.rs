mod client;
mod config;
mod kernel;

use anyhow::{Context, Result};
use clap::Parser;
use log::{error, info};
use std::process::{Command, Stdio};

use crate::client::{DesktopToken, KernelClient};
use crate::config::{Cli, Commands, PackShellConfig};
use crate::kernel::KernelProcess;

fn main() {
    env_logger::init();

    let cli = Cli::parse();

    let exit_code = match cli.command {
        Commands::Run {
            pack_id,
            command,
            port,
            kernel_cmd,
            api_token,
            timeout,
            working_dir,
        } => {
            let config = PackShellConfig::from_run_args(
                pack_id,
                command,
                port,
                kernel_cmd,
                api_token,
                timeout,
                working_dir,
            );
            match run(config) {
                Ok(code) => code,
                Err(e) => {
                    error!("Fatal error: {:#}", e);
                    1
                }
            }
        }
        Commands::Version => {
            println!("pack-shell {}", env!("CARGO_PKG_VERSION"));
            0
        }
    };

    std::process::exit(exit_code);
}

fn run(config: PackShellConfig) -> Result<i32> {
    let client = KernelClient::new(config.port, config.api_token.clone());

    // Step 1: Check if kernel is healthy
    info!("Checking kernel health on port {}...", config.port);
    let mut _kernel_process: Option<KernelProcess> = None;

    if !client.is_healthy() {
        // Step 2: Start kernel
        info!(
            "Kernel not responding. Starting with: {}",
            config.kernel_cmd
        );
        let mut kp = KernelProcess::new(config.kernel_cmd.clone());
        kp.start(config.port)
            .context("Failed to start kernel process")?;
        _kernel_process = Some(kp);

        // Step 3: Wait for kernel to become healthy
        info!(
            "Waiting for kernel to become healthy (timeout: {}s)...",
            config.timeout
        );
        client
            .wait_for_healthy(config.timeout)
            .context("Kernel did not become healthy within timeout")?;
        info!("Kernel is healthy.");
    } else {
        info!("Kernel is already healthy.");
    }

    // Step 4: Get desktop token
    info!("Requesting desktop token for pack: {}", config.pack_id);
    let token_response = client
        .get_desktop_token(&config.pack_id)
        .context("Failed to get desktop token")?;
    info!(
        "Desktop token acquired (expires in {}s).",
        token_response.expires_in
    );

    // Step 5: Launch app subprocess
    info!("Launching app: {}", config.command);
    let parts: Vec<String> = shell_words::split(&config.command)
        .context("Failed to parse --command (unmatched quote?)")?;
    if parts.is_empty() {
        anyhow::bail!("--command is empty");
    }

    let program = &parts[0];
    let args = &parts[1..];

    let mut cmd = build_app_command(program, args, &token_response, &config);

    let mut child = cmd
        .spawn()
        .context(format!("Failed to spawn: {}", program))?;

    let status = child.wait().context("Failed to wait for app process")?;

    let exit_code = status.code().unwrap_or(1);
    info!("App exited with code: {}", exit_code);

    Ok(exit_code)
}

fn build_app_command(
    program: &str,
    args: &[String],
    token_response: &DesktopToken,
    config: &PackShellConfig,
) -> Command {
    let mut cmd = Command::new(program);
    cmd.args(args)
        .env("RUMI_TOKEN", &token_response.token)
        .env("RUMI_PORT", token_response.port.to_string())
        .env("RUMI_PACK_ID", &config.pack_id)
        .env_remove("RUMI_API_TOKEN")
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .stdin(Stdio::inherit());

    if let Some(ref dir) = config.working_dir {
        cmd.current_dir(dir);
    }

    cmd
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsStr;

    #[test]
    fn app_command_removes_admin_api_token_from_child_environment() {
        let token_response = DesktopToken {
            token: "desktop-token".to_string(),
            port: 8765,
            expires_in: 60,
        };
        let config = PackShellConfig {
            pack_id: "test-pack".to_string(),
            port: 8765,
            kernel_cmd: "python -m rumi_ai".to_string(),
            api_token: "admin-token".to_string(),
            timeout: 60,
            command: "echo ok".to_string(),
            working_dir: None,
        };

        let cmd = build_app_command("echo", &["ok".to_string()], &token_response, &config);
        let envs: Vec<_> = cmd.get_envs().collect();

        assert!(envs
            .iter()
            .any(|(key, value)| { *key == OsStr::new("RUMI_API_TOKEN") && value.is_none() }));
        assert!(envs.iter().any(|(key, value)| {
            *key == OsStr::new("RUMI_TOKEN") && value == &Some(OsStr::new("desktop-token"))
        }));
        assert!(envs.iter().any(|(key, value)| {
            *key == OsStr::new("RUMI_PORT") && value == &Some(OsStr::new("8765"))
        }));
        assert!(envs.iter().any(|(key, value)| {
            *key == OsStr::new("RUMI_PACK_ID") && value == &Some(OsStr::new("test-pack"))
        }));
    }
}
