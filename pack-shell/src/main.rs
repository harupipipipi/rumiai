mod client;
mod config;
mod kernel;

use anyhow::{Context, Result};
use clap::Parser;
use log::{error, info};
use std::process::{Command, Stdio};

use crate::client::KernelClient;
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
        info!("Kernel not responding. Starting with: {}", config.kernel_cmd);
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
    info!("Desktop token acquired (expires in {}s).", token_response.expires_in);

    // Step 5: Launch app subprocess
    info!("Launching app: {}", config.command);
    let parts: Vec<&str> = config.command.split_whitespace().collect();
    if parts.is_empty() {
        anyhow::bail!("--command is empty");
    }

    let program = parts[0];
    let args = &parts[1..];

    let mut cmd = Command::new(program);
    cmd.args(args)
        .env("RUMI_TOKEN", &token_response.token)
        .env("RUMI_PORT", token_response.port.to_string())
        .env("RUMI_PACK_ID", &config.pack_id)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .stdin(Stdio::inherit());

    if let Some(ref dir) = config.working_dir {
        cmd.current_dir(dir);
    }

    let mut child = cmd.spawn().context(format!("Failed to spawn: {}", program))?;

    let status = child.wait().context("Failed to wait for app process")?;

    let exit_code = status.code().unwrap_or(1);
    info!("App exited with code: {}", exit_code);

    Ok(exit_code)
}
