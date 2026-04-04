use clap::{Parser, Subcommand};

const DEFAULT_KERNEL_CMD: &str = "python -m rumi_ai";

/// Pack desktop app launcher
#[derive(Parser, Debug)]
#[command(name = "pack-shell", version, about = "Pack desktop app launcher")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    /// Launch a pack desktop app
    Run {
        /// Pack ID to launch
        pack_id: String,

        /// Command to execute
        #[arg(long)]
        command: String,

        /// Kernel API port
        #[arg(long, default_value_t = 8765)]
        port: u16,

        /// Command to start the kernel if not running
        #[arg(long, default_value = DEFAULT_KERNEL_CMD)]
        kernel_cmd: String,

        /// API token (falls back to RUMI_API_TOKEN env var)
        #[arg(long, env = "RUMI_API_TOKEN")]
        api_token: String,

        /// Kernel startup timeout in seconds
        #[arg(long, default_value_t = 60)]
        timeout: u64,

        /// Working directory for the launched app
        #[arg(long)]
        working_dir: Option<String>,
    },
    /// Show version information
    Version,
}

/// Runtime configuration built from CLI arguments
pub struct PackShellConfig {
    pub pack_id: String,
    pub port: u16,
    pub kernel_cmd: String,
    pub api_token: String,
    pub timeout: u64,
    pub command: String,
    pub working_dir: Option<String>,
}

impl PackShellConfig {
    pub fn from_run_args(
        pack_id: String,
        command: String,
        port: u16,
        kernel_cmd: String,
        api_token: String,
        timeout: u64,
        working_dir: Option<String>,
    ) -> Self {
        Self {
            pack_id,
            port,
            kernel_cmd,
            api_token,
            timeout,
            command,
            working_dir,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pack_shell_config_from_run_args() {
        let config = PackShellConfig::from_run_args(
            "test-pack-123".to_string(),
            "python app.py".to_string(),
            8765,
            DEFAULT_KERNEL_CMD.to_string(),
            "test-token-abc".to_string(),
            60,
            Some("/tmp/work".to_string()),
        );
        assert_eq!(config.pack_id, "test-pack-123");
        assert_eq!(config.command, "python app.py");
        assert_eq!(config.port, 8765);
        assert_eq!(config.kernel_cmd, DEFAULT_KERNEL_CMD);
        assert_eq!(config.api_token, "test-token-abc");
        assert_eq!(config.timeout, 60);
        assert_eq!(config.working_dir, Some("/tmp/work".to_string()));
    }

    #[test]
    fn test_pack_shell_config_without_working_dir() {
        let config = PackShellConfig::from_run_args(
            "pack-456".to_string(),
            "node index.js".to_string(),
            9000,
            DEFAULT_KERNEL_CMD.to_string(),
            "token-xyz".to_string(),
            30,
            None,
        );
        assert_eq!(config.pack_id, "pack-456");
        assert_eq!(config.port, 9000);
        assert_eq!(config.timeout, 30);
        assert!(config.working_dir.is_none());
    }
}
