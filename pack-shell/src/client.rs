use anyhow::{bail, Context, Result};
use log::debug;
use serde::Deserialize;
use std::time::Duration;

/// Response from POST /api/desktop/token
#[derive(Debug, Deserialize)]
pub struct DesktopToken {
    pub token: String,
    pub port: u16,
    pub expires_in: u64,
}

/// Wrapper for the API response envelope
#[derive(Debug, Deserialize)]
#[serde(bound(deserialize = "T: serde::Deserialize<'de>"))]
struct ApiResponse<T> {
    success: bool,
    #[serde(default)]
    data: Option<T>,
    #[serde(default)]
    error: Option<String>,
}

/// REST client for the Kernel API
pub struct KernelClient {
    port: u16,
    api_token: String,
    http: reqwest::blocking::Client,
}

impl KernelClient {
    pub fn new(port: u16, api_token: String) -> Self {
        let http = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(3))
            .build()
            .expect("Failed to build HTTP client");
        Self {
            port,
            api_token,
            http,
        }
    }

    fn base_url(&self) -> String {
        format!("http://127.0.0.1:{}", self.port)
    }

    /// Check if the kernel is healthy.
    /// Returns true if GET /health returns status=="ok".
    pub fn is_healthy(&self) -> bool {
        let url = format!("{}/health", self.base_url());
        debug!("GET {}", url);

        match self.http.get(&url).send() {
            Ok(resp) => {
                if !resp.status().is_success() {
                    debug!("Health check returned status: {}", resp.status());
                    return false;
                }
                match resp.json::<serde_json::Value>() {
                    Ok(body) => health_status(&body) == Some("ok"),
                    Err(e) => {
                        debug!("Failed to parse health response: {}", e);
                        false
                    }
                }
            }
            Err(e) => {
                debug!("Health check failed: {}", e);
                false
            }
        }
    }

    /// Poll /health until it returns ok or timeout is reached.
    pub fn wait_for_healthy(&self, timeout_secs: u64) -> Result<()> {
        let start = std::time::Instant::now();
        let timeout = Duration::from_secs(timeout_secs);

        loop {
            if self.is_healthy() {
                return Ok(());
            }

            if start.elapsed() >= timeout {
                bail!(
                    "Kernel did not become healthy within {} seconds",
                    timeout_secs
                );
            }

            debug!("Kernel not ready, retrying in 1s...");
            std::thread::sleep(Duration::from_secs(1));
        }
    }

    /// Request a desktop token from POST /api/desktop/token.
    pub fn get_desktop_token(&self, pack_id: &str) -> Result<DesktopToken> {
        let url = format!("{}/api/desktop/token", self.base_url());
        debug!("POST {}", url);

        let body = serde_json::json!({
            "pack_id": pack_id
        });

        let resp = self
            .http
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_token))
            .json(&body)
            .send()
            .context("Failed to send token request")?;

        let status = resp.status();
        if !status.is_success() {
            let text = resp.text().unwrap_or_default();
            bail!("Token request failed (HTTP {}): {}", status, text);
        }

        let api_resp: ApiResponse<DesktopToken> =
            resp.json().context("Failed to parse token response")?;

        if !api_resp.success {
            bail!(
                "Token request returned success=false: {}",
                api_resp
                    .error
                    .unwrap_or_else(|| "unknown error".to_string())
            );
        }

        api_resp.data.context("Token response missing 'data' field")
    }
}

fn health_status(body: &serde_json::Value) -> Option<&str> {
    body.get("status")
        .and_then(|value| value.as_str())
        .or_else(|| {
            body.get("data")
                .and_then(|value| value.as_object())
                .and_then(|data| data.get("status"))
                .and_then(|value| value.as_str())
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_desktop_token_deserialize() {
        let json = r#"{"token": "abc-123-xyz", "port": 8765, "expires_in": 3600}"#;
        let token: DesktopToken = serde_json::from_str(json).unwrap();
        assert_eq!(token.token, "abc-123-xyz");
        assert_eq!(token.port, 8765);
        assert_eq!(token.expires_in, 3600);
    }

    #[test]
    fn test_api_response_success_deserialize() {
        let json = r#"{
            "success": true,
            "data": {"token": "tok-999", "port": 9000, "expires_in": 1800}
        }"#;
        let resp: ApiResponse<DesktopToken> = serde_json::from_str(json).unwrap();
        assert!(resp.success);
        assert!(resp.data.is_some());
        let data = resp.data.unwrap();
        assert_eq!(data.token, "tok-999");
        assert_eq!(data.port, 9000);
        assert_eq!(data.expires_in, 1800);
    }

    #[test]
    fn test_api_response_failure_deserialize() {
        let json = r#"{"success": false, "error": "unauthorized"}"#;
        let resp: ApiResponse<DesktopToken> = serde_json::from_str(json).unwrap();
        assert!(!resp.success);
        assert!(resp.data.is_none());
        assert_eq!(resp.error, Some("unauthorized".to_string()));
    }

    #[test]
    fn test_health_status_reads_top_level_status() {
        let body = json!({
            "status": "ok"
        });
        assert_eq!(health_status(&body), Some("ok"));
    }

    #[test]
    fn test_health_status_reads_enveloped_status() {
        let body = json!({
            "success": true,
            "data": {
                "status": "ok"
            }
        });
        assert_eq!(health_status(&body), Some("ok"));
    }

    #[test]
    fn test_health_status_returns_none_when_missing() {
        let body = json!({
            "success": true,
            "data": {
                "runtime_ready": true
            }
        });
        assert_eq!(health_status(&body), None);
    }
}
