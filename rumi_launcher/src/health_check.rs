//! Kernel health-check via HTTP.
//!
//! The Kernel exposes `GET /health` on its API port (default 8765).
//! A 200 response means the Kernel is ready to serve requests.

use std::time::Duration;

use anyhow::{bail, Context, Result};
use log::info;

/// Send a single health-check request.
///
/// Returns `Ok(true)` if the Kernel responded with HTTP 200,
/// `Ok(false)` for any other status or a connection error.
pub fn check_health(port: u16) -> Result<bool> {
    let url = format!("http://localhost:{port}/health");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
        .context("failed to build health-check HTTP client")?;

    match client.get(&url).send() {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

/// Poll `GET /health` until the Kernel is ready or `timeout_secs` elapses.
///
/// Checks once per second.
pub fn wait_for_healthy(port: u16, timeout_secs: u64) -> Result<()> {
    info!(
        "Waiting for Kernel health-check on port {port} (timeout {timeout_secs}s) ..."
    );

    for elapsed in 0..timeout_secs {
        if check_health(port)? {
            info!("Kernel healthy after ~{elapsed}s");
            return Ok(());
        }
        std::thread::sleep(Duration::from_secs(1));
    }

    bail!("Kernel did not become healthy within {timeout_secs}s on port {port}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_health_unreachable_port() {
        let result = check_health(1);
        assert!(result.is_ok());
        assert!(!result.unwrap());
    }
}
