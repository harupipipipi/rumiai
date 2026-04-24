//! Kernel health-check via HTTP.
//!
//! The Kernel exposes `GET /health` on its API port (default 8765).
//! A 200 response means the Kernel is ready to serve requests.

use std::sync::OnceLock;
use std::time::Duration;

use anyhow::{bail, Result};
use log::info;
use serde::Deserialize;

/// Reusable blocking HTTP client for health checks.
static HEALTH_CLIENT: OnceLock<reqwest::blocking::Client> = OnceLock::new();

#[derive(Debug, Deserialize)]
struct ApiEnvelope<T> {
    success: bool,
    data: Option<T>,
}

#[derive(Debug, Deserialize)]
struct HealthPayload {
    panel_ready: Option<bool>,
}

fn health_client() -> &'static reqwest::blocking::Client {
    HEALTH_CLIENT.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(Duration::from_millis(800))
            .build()
            .expect("failed to build health-check HTTP client")
    })
}

/// Send a single health-check request.
///
/// Returns `Ok(true)` if the Kernel responded with HTTP 200,
/// `Ok(false)` for any other status or a connection error.
pub fn check_health(port: u16) -> Result<bool> {
    let url = format!("http://127.0.0.1:{port}/health");

    match health_client().get(&url).send() {
        Ok(resp) => {
            if !resp.status().is_success() {
                return Ok(false);
            }

            let envelope: ApiEnvelope<HealthPayload> = match resp.json() {
                Ok(payload) => payload,
                Err(_) => return Ok(true),
            };

            if !envelope.success {
                return Ok(false);
            }

            Ok(envelope
                .data
                .and_then(|payload| payload.panel_ready)
                .unwrap_or(true))
        }
        Err(_) => Ok(false),
    }
}

/// Poll `GET /health` until the Kernel is ready or `timeout_secs` elapses.
///
/// Checks every 200 ms.
pub fn wait_for_healthy(port: u16, timeout_secs: u64) -> Result<()> {
    info!(
        "Waiting for Kernel health-check on port {port} (timeout {timeout_secs}s) ..."
    );

    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(timeout_secs);
    let interval = Duration::from_millis(200);

    while start.elapsed() < timeout {
        if check_health(port)? {
            info!("Kernel healthy after ~{:?}", start.elapsed());
            return Ok(());
        }
        std::thread::sleep(interval);
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
