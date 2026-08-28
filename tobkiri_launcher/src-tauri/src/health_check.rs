//! Kernel health-check via HTTP.
//!
//! The Kernel exposes `GET /health` on its API port (default 8765).
//! A 200 response means the Kernel is ready to serve requests.

use std::collections::BTreeMap;
use std::sync::OnceLock;
use std::time::Duration;

use anyhow::{bail, Result};
use log::info;
use rand::{distributions::Alphanumeric, Rng};
use serde::Deserialize;
use sha2::{Digest, Sha256};

/// Reusable blocking HTTP client for health checks.
static HEALTH_CLIENT: OnceLock<reqwest::blocking::Client> = OnceLock::new();
static UI_READINESS_CLIENT: OnceLock<reqwest::blocking::Client> = OnceLock::new();

#[derive(Debug, Deserialize)]
struct ApiEnvelope<T> {
    success: bool,
    data: Option<T>,
}

#[derive(Debug, Deserialize)]
struct HealthPayload {
    panel_ready: Option<bool>,
    runtime_ready: Option<bool>,
    desktop_challenge_response: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct UIReadinessProbe {
    pub(crate) status: String,
    pub(crate) code: String,
}

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct UIReadinessPayload {
    pub(crate) schema: String,
    pub(crate) status: String,
    pub(crate) ready: bool,
    pub(crate) mode: Option<String>,
    pub(crate) probes: BTreeMap<String, UIReadinessProbe>,
    desktop_challenge_response: Option<String>,
}

const DESKTOP_HEALTH_CHALLENGE_HEADER: &str = "X-Rumi-Desktop-Health-Challenge";
const UI_READINESS_AUTHORIZATION_HEADER: &str = "X-Tobkiri-UI-Readiness-Authorization";
const UI_READINESS_SCHEMA: &str = "io.tobkiri.ui-readiness.v1";
const PROFILE_RECONFIRMATION_MODE: &str = "profile_reconfirmation_required";
const DESKTOP_HEALTH_KEY_LABEL: &str = "tobkiri-desktop-health-key-v1";
const UI_READINESS_KEY_LABEL: &str = "tobkiri-ui-readiness-key-v1";
const REQUIRED_UI_READINESS_PROBES: [&str; 9] = [
    "static_bundle",
    "chat_route",
    "ui_catalog",
    "settings",
    "model_catalog",
    "tool_catalog",
    "conversation_bootstrap",
    "default_conversation_load",
    "auth_session",
];

fn generate_health_challenge() -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect()
}

fn hex_lower(bytes: &[u8]) -> String {
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push_str(&format!("{byte:02x}"));
    }
    output
}

fn constant_time_hex_eq(actual: &str, expected: &str) -> bool {
    if actual.len() != expected.len() || actual.len() != 64 {
        return false;
    }
    let mut difference = 0_u8;
    for (left, right) in actual.bytes().zip(expected.bytes()) {
        difference |= left ^ right;
    }
    difference == 0
}

pub(crate) fn hmac_sha256_hex(secret: &str, message: &str) -> String {
    const BLOCK_SIZE: usize = 64;

    let mut key = secret.as_bytes().to_vec();
    if key.len() > BLOCK_SIZE {
        key = Sha256::digest(&key).to_vec();
    }
    key.resize(BLOCK_SIZE, 0);

    let mut outer_key_pad = [0x5c; BLOCK_SIZE];
    let mut inner_key_pad = [0x36; BLOCK_SIZE];
    for (idx, byte) in key.iter().enumerate() {
        outer_key_pad[idx] ^= byte;
        inner_key_pad[idx] ^= byte;
    }

    let mut inner = Sha256::new();
    inner.update(inner_key_pad);
    inner.update(message.as_bytes());
    let inner_hash = inner.finalize();

    let mut outer = Sha256::new();
    outer.update(outer_key_pad);
    outer.update(inner_hash);
    hex_lower(&outer.finalize())
}

pub(crate) fn ui_readiness_request_proof(secret: &str, challenge: &str) -> String {
    domain_separated_proof(
        secret,
        UI_READINESS_KEY_LABEL,
        &format!("request:{challenge}"),
    )
}

pub(crate) fn ui_readiness_response_proof(secret: &str, challenge: &str) -> String {
    domain_separated_proof(
        secret,
        UI_READINESS_KEY_LABEL,
        &format!("response:{challenge}"),
    )
}

fn desktop_health_response_proof(secret: &str, challenge: &str) -> String {
    domain_separated_proof(secret, DESKTOP_HEALTH_KEY_LABEL, challenge)
}

fn domain_separated_proof(secret: &str, label: &str, message: &str) -> String {
    let derived_key = hmac_sha256_hex(secret, label);
    hmac_sha256_hex(&derived_key, message)
}

pub(crate) fn ui_readiness_allows_launch(payload: &UIReadinessPayload) -> bool {
    payload.ready
        && (payload.status == "UP"
            || (payload.status == "DEGRADED"
                && payload.mode.as_deref() == Some(PROFILE_RECONFIRMATION_MODE)))
}

fn health_client() -> &'static reqwest::blocking::Client {
    HEALTH_CLIENT.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(Duration::from_millis(800))
            .build()
            .expect("failed to build health-check HTTP client")
    })
}

fn ui_readiness_client() -> &'static reqwest::blocking::Client {
    UI_READINESS_CLIENT.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(Duration::from_millis(3_500))
            .build()
            .expect("failed to build UI-readiness HTTP client")
    })
}

/// Fetch a complete UI readiness assessment and authenticate the listener.
pub(crate) fn check_authenticated_ui_readiness(
    port: u16,
    bootstrap_secret: &str,
) -> Result<Option<UIReadinessPayload>> {
    if bootstrap_secret.is_empty() {
        return Ok(None);
    }
    let challenge = generate_health_challenge();
    let url = format!("http://127.0.0.1:{port}/ui-readiness");
    let response = match ui_readiness_client()
        .get(url)
        .header(DESKTOP_HEALTH_CHALLENGE_HEADER, &challenge)
        .header(
            UI_READINESS_AUTHORIZATION_HEADER,
            ui_readiness_request_proof(bootstrap_secret, &challenge),
        )
        .send()
    {
        Ok(response) => response,
        Err(_) => return Ok(None),
    };
    if !response.status().is_success() {
        return Ok(None);
    }
    let envelope: ApiEnvelope<UIReadinessPayload> = match response.json() {
        Ok(payload) => payload,
        Err(_) => return Ok(None),
    };
    if !envelope.success {
        return Ok(None);
    }
    let Some(payload) = envelope.data else {
        return Ok(None);
    };
    let expected = ui_readiness_response_proof(bootstrap_secret, &challenge);
    let authenticated = payload
        .desktop_challenge_response
        .as_deref()
        .is_some_and(|actual| constant_time_hex_eq(actual, &expected));
    let complete = payload.schema == UI_READINESS_SCHEMA
        && REQUIRED_UI_READINESS_PROBES.iter().all(|name| {
            payload.probes.get(*name).is_some_and(|probe| {
                matches!(
                    probe.status.as_str(),
                    "UP" | "DOWN" | "DEGRADED" | "UNKNOWN"
                ) && !probe.code.trim().is_empty()
            })
        });
    if !authenticated || !complete {
        return Ok(None);
    }
    Ok(Some(payload))
}

fn fetch_authenticated_health(port: u16, bootstrap_secret: &str) -> Result<Option<HealthPayload>> {
    if bootstrap_secret.is_empty() {
        return Ok(None);
    }

    let challenge = generate_health_challenge();
    let url = format!("http://127.0.0.1:{port}/health");
    let resp = match health_client()
        .get(&url)
        .header(DESKTOP_HEALTH_CHALLENGE_HEADER, &challenge)
        .send()
    {
        Ok(resp) => resp,
        Err(_) => return Ok(None),
    };

    if !resp.status().is_success() {
        return Ok(None);
    }

    let envelope: ApiEnvelope<HealthPayload> = match resp.json() {
        Ok(payload) => payload,
        Err(_) => return Ok(None),
    };
    if !envelope.success {
        return Ok(None);
    }

    let Some(payload) = envelope.data else {
        return Ok(None);
    };
    if payload.panel_ready == Some(false) {
        return Ok(None);
    }

    let expected = desktop_health_response_proof(bootstrap_secret, &challenge);
    if !payload
        .desktop_challenge_response
        .as_deref()
        .is_some_and(|actual| constant_time_hex_eq(actual, &expected))
    {
        return Ok(None);
    }
    Ok(Some(payload))
}

/// Send a health-check request that proves the listener knows the desktop
/// bootstrap secret without disclosing that secret to an untrusted local port.
pub fn check_authenticated_health(port: u16, bootstrap_secret: &str) -> Result<bool> {
    Ok(fetch_authenticated_health(port, bootstrap_secret)?.is_some())
}

/// Return whether an authenticated Kernel has completed runtime activation.
pub fn check_authenticated_runtime_ready(port: u16, bootstrap_secret: &str) -> Result<bool> {
    Ok(fetch_authenticated_health(port, bootstrap_secret)?
        .and_then(|payload| payload.runtime_ready)
        .unwrap_or(false))
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
    info!("Waiting for Kernel health-check on port {port} (timeout {timeout_secs}s) ...");

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

    #[test]
    fn hmac_sha256_hex_matches_known_vector() {
        assert_eq!(
            hmac_sha256_hex("key", "The quick brown fox jumps over the lazy dog"),
            "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"
        );
    }

    #[test]
    fn health_signing_oracle_cannot_forge_ui_readiness_authorization() {
        let secret = "launcher-bootstrap-secret";
        let challenge = "attacker-selected";
        let health_oracle =
            desktop_health_response_proof(secret, &format!("ui-readiness-request:{challenge}"));

        assert_ne!(health_oracle, ui_readiness_request_proof(secret, challenge));
        assert_ne!(
            ui_readiness_request_proof(secret, challenge),
            ui_readiness_response_proof(secret, challenge)
        );
    }

    #[test]
    fn constant_time_hex_comparison_rejects_wrong_case_length_and_value() {
        let expected = "a".repeat(64);
        assert!(constant_time_hex_eq(&expected, &expected));
        assert!(!constant_time_hex_eq(&"A".repeat(64), &expected));
        assert!(!constant_time_hex_eq(&"a".repeat(63), &expected));
        assert!(!constant_time_hex_eq(
            &format!("{}b", "a".repeat(63)),
            &expected
        ));
    }

    #[test]
    fn degraded_readiness_requires_the_profile_reconfirmation_mode() {
        let mut payload = UIReadinessPayload {
            schema: UI_READINESS_SCHEMA.to_string(),
            status: "DEGRADED".to_string(),
            ready: true,
            mode: None,
            probes: BTreeMap::new(),
            desktop_challenge_response: None,
        };
        assert!(!ui_readiness_allows_launch(&payload));

        payload.mode = Some(PROFILE_RECONFIRMATION_MODE.to_string());
        assert!(ui_readiness_allows_launch(&payload));
    }
}
