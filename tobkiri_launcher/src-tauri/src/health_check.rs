//! Kernel health-check via HTTP.
//!
//! The Kernel exposes `GET /health` on its API port (default 8765).
//! A 200 response means the Kernel is ready to serve requests.

use std::sync::OnceLock;
use std::time::Duration;

use anyhow::{bail, Context, Result};
use log::info;
use rand::{distributions::Alphanumeric, Rng, RngCore};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::host_contract::ExecutionProfileIdentity;

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
    runtime_ready: Option<bool>,
    desktop_challenge_response: Option<String>,
    profile_id: Option<String>,
    profile_revision: Option<String>,
    activation_id: Option<String>,
    plan_digest: Option<String>,
}

const DESKTOP_HEALTH_CHALLENGE_HEADER: &str = "X-Rumi-Desktop-Health-Challenge";

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

fn hmac_sha256_hex(secret: &str, message: &str) -> String {
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

fn health_client() -> &'static reqwest::blocking::Client {
    HEALTH_CLIENT.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(Duration::from_millis(800))
            .build()
            .expect("failed to build health-check HTTP client")
    })
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

    let expected = hmac_sha256_hex(bootstrap_secret, &challenge);
    if !payload
        .desktop_challenge_response
        .as_deref()
        .is_some_and(|actual| actual.eq_ignore_ascii_case(&expected))
    {
        return Ok(None);
    }
    Ok(Some(payload))
}

/// Capture the exact active execution identity from an authenticated runtime.
///
/// Newer runtimes may project the tuple directly on /health. The canonical
/// fallback uses the existing one-time panel bootstrap and the committed
/// profile.read contract, so this function never trusts a client-supplied
/// profile ID or a launcher-side Defaults constant.
pub(crate) fn authenticated_runtime_identity(
    port: u16,
    bootstrap_secret: &str,
) -> Result<ExecutionProfileIdentity> {
    let health = fetch_authenticated_health(port, bootstrap_secret)?
        .context("authenticated runtime health is unavailable")?;
    if let Some(identity) = identity_from_health(&health)? {
        return Ok(identity);
    }

    let code = crate::request_panel_bootstrap_code_with_retry(port, bootstrap_secret)
        .context("failed to issue a profile identity bootstrap code")?;
    let origin = format!("http://127.0.0.1:{port}");
    let exchange = health_client()
        .post(format!("{origin}/api/panel/auth/exchange"))
        .header("Origin", &origin)
        .json(&PanelExchangeRequest { code })
        .send()
        .context("profile identity panel exchange failed")?;
    if !exchange.status().is_success() {
        bail!(
            "profile identity panel exchange returned {}",
            exchange.status()
        );
    }
    let cookie = exchange
        .headers()
        .get_all(reqwest::header::SET_COOKIE)
        .iter()
        .find_map(|value| {
            let value = value.to_str().ok()?;
            let (name, rest) = value.split_once('=')?;
            (name.trim() == "rumi_panel_session")
                .then(|| rest.split(';').next().unwrap_or_default().trim())
        })
        .filter(|value| !value.is_empty())
        .context("profile identity panel exchange did not return a session cookie")?;

    let profile = health_client()
        .get(format!(
            "{origin}/api/contracts/defaultspack/GET%20%2Fapi%2Fruntime-surface%2Fprofile"
        ))
        .header(
            reqwest::header::COOKIE,
            format!("rumi_panel_session={cookie}"),
        )
        .header("X-Tobkiri-Request-ID", random_uuid_v4())
        .send()
        .context("canonical runtime profile read failed")?;
    if !profile.status().is_success() {
        bail!(
            "canonical runtime profile read returned {}",
            profile.status()
        );
    }
    let envelope: ApiEnvelope<Value> = profile
        .json()
        .context("canonical runtime profile response is malformed")?;
    if !envelope.success {
        bail!("canonical runtime profile read was rejected");
    }
    let data = envelope
        .data
        .context("canonical runtime profile response has no data")?;
    identity_from_runtime_surface(&data)
}

#[derive(Debug, Serialize)]
struct PanelExchangeRequest {
    code: String,
}

fn identity_from_health(payload: &HealthPayload) -> Result<Option<ExecutionProfileIdentity>> {
    let values = (
        payload.profile_id.as_deref(),
        payload.profile_revision.as_deref(),
        payload.activation_id.as_deref(),
        payload.plan_digest.as_deref(),
    );
    if values.0.is_none() && values.1.is_none() && values.2.is_none() && values.3.is_none() {
        return Ok(None);
    }
    let identity = ExecutionProfileIdentity::new(
        values.0.context("health profile_id is incomplete")?,
        values.1.context("health profile_revision is incomplete")?,
        values.2.context("health activation_id is incomplete")?,
        values.3.context("health plan_digest is incomplete")?,
    )?;
    Ok(Some(identity))
}

fn identity_from_runtime_surface(data: &Value) -> Result<ExecutionProfileIdentity> {
    let profile_id = data
        .get("profile_id")
        .and_then(Value::as_str)
        .context("runtime profile response is missing profile_id")?;
    let profile_revision = data
        .get("profile_revision")
        .and_then(Value::as_str)
        .context("runtime profile response is missing profile_revision")?;
    let plan_digest = data
        .get("plan_digest")
        .and_then(Value::as_str)
        .context("runtime profile response is missing plan_digest")?;
    let activation_id = data
        .get("activation_id")
        .and_then(Value::as_str)
        .or_else(|| {
            data.get("activation_record")
                .and_then(|value| value.get("activation_id"))
                .and_then(Value::as_str)
        })
        .or_else(|| {
            data.get("data")
                .and_then(|value| value.get("activation_record"))
                .and_then(|value| value.get("activation_id"))
                .and_then(Value::as_str)
        })
        .context("runtime profile response is missing activation_id")?;
    ExecutionProfileIdentity::new(profile_id, profile_revision, activation_id, plan_digest)
}

fn random_uuid_v4() -> String {
    let mut bytes = [0_u8; 16];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0],
        bytes[1],
        bytes[2],
        bytes[3],
        bytes[4],
        bytes[5],
        bytes[6],
        bytes[7],
        bytes[8],
        bytes[9],
        bytes[10],
        bytes[11],
        bytes[12],
        bytes[13],
        bytes[14],
        bytes[15]
    )
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
    fn runtime_surface_identity_requires_all_four_bindings() {
        let data = serde_json::json!({
            "profile_id": "profile-a",
            "profile_revision": format!("sha256:{}", "a".repeat(64)),
            "plan_digest": format!("sha256:{}", "b".repeat(64)),
            "data": {
                "activation_record": {"activation_id": "activation:profile-a-2026"}
            }
        });
        let identity = identity_from_runtime_surface(&data).unwrap();
        assert_eq!(identity.profile_id, "profile-a");
        assert_eq!(identity.activation_id, "activation:profile-a-2026");
    }

    #[test]
    fn runtime_surface_identity_rejects_missing_activation_binding() {
        let data = serde_json::json!({
            "profile_id": "profile-a",
            "profile_revision": format!("sha256:{}", "a".repeat(64)),
            "plan_digest": format!("sha256:{}", "b".repeat(64))
        });
        assert!(identity_from_runtime_surface(&data).is_err());
    }
}
