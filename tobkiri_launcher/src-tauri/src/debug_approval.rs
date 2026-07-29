use std::collections::HashSet;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use hmac::{Hmac, Mac};
use rand::{distributions::Alphanumeric, Rng, RngCore};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};

type HmacSha256 = Hmac<Sha256>;

const ARMED_TTL_SECONDS: u64 = 5 * 60;
const ACTIVE_TTL_SECONDS: u64 = 30 * 60;

#[derive(Debug, Clone)]
enum LeaseState {
    Disabled { reason: String },
    Armed { expires_at: u64 },
    Active(ActiveLease),
}

#[derive(Debug, Clone)]
struct ActiveLease {
    session_id: String,
    run_id: String,
    workspace: PathBuf,
    workspace_digest: String,
    pack_id: String,
    profile_id: String,
    process_id: u32,
    expires_at: u64,
    lease_hash: String,
}

#[derive(Debug)]
struct DebugApprovalState {
    lease: LeaseState,
    signed_requests: HashSet<String>,
    verified_requests: HashSet<String>,
}

#[derive(Debug)]
pub struct DebugApprovalManager {
    state: Mutex<DebugApprovalState>,
    instance_nonce: String,
    signing_key: [u8; 32],
    audit_path: PathBuf,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct DebugApprovalStatus {
    pub state: String,
    pub reason: Option<String>,
    pub armed_remaining_seconds: Option<u64>,
    pub session_id: Option<String>,
    pub run_id: Option<String>,
    pub workspace: Option<String>,
    pub workspace_digest: Option<String>,
    pub pack_id: Option<String>,
    pub profile_id: Option<String>,
    pub expires_at: Option<u64>,
    pub instance_nonce: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugSessionStartRequest {
    pub session_id: String,
    pub run_id: String,
    pub workspace: String,
    pub pack_id: String,
    pub profile_id: String,
    #[serde(default)]
    pub process_id: Option<u32>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugSessionStopRequest {
    pub session_id: String,
    pub run_id: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugOperatorRequest {
    pub session_id: String,
    pub run_id: String,
    pub workspace_digest: String,
    pub request_id: String,
    pub permission_id: String,
    pub tool: String,
    pub action: String,
    pub operation: String,
    pub canonical_arguments_digest: String,
    #[serde(default)]
    pub target_digest: Option<String>,
    pub conversation_owner: String,
    pub request_expires_at: u64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugOperatorVerifyRequest {
    pub debug_cli_operator: DebugCliOperator,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DebugCliOperator {
    pub kind: String,
    pub version: u8,
    pub origin: String,
    pub scope: String,
    pub session_id: String,
    pub run_id: String,
    pub workspace_digest: String,
    pub request_id: String,
    pub permission_id: String,
    pub tool: String,
    pub action: String,
    pub operation: String,
    pub canonical_arguments_digest: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_digest: Option<String>,
    pub conversation_owner: String,
    pub issued_at: u64,
    pub expires_at: u64,
    pub nonce: String,
    pub signature: String,
}

impl DebugApprovalManager {
    pub fn new(audit_path: PathBuf) -> Self {
        let mut signing_key = [0_u8; 32];
        rand::thread_rng().fill_bytes(&mut signing_key);
        Self {
            state: Mutex::new(DebugApprovalState {
                lease: LeaseState::Disabled {
                    reason: "launcher_started".to_string(),
                },
                signed_requests: HashSet::new(),
                verified_requests: HashSet::new(),
            }),
            instance_nonce: random_identifier("launcher"),
            signing_key,
            audit_path,
        }
    }

    pub fn status(&self) -> DebugApprovalStatus {
        self.status_at(now_epoch_seconds())
    }

    fn status_at(&self, now: u64) -> DebugApprovalStatus {
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        expire_if_needed(&mut state, now);
        status_from_state(&state.lease, &self.instance_nonce, now)
    }

    pub fn arm(&self, confirmed: bool) -> Result<DebugApprovalStatus, String> {
        if !confirmed {
            return Err("explicit confirmation is required".to_string());
        }
        let now = now_epoch_seconds();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        if !matches!(state.lease, LeaseState::Disabled { .. }) {
            return Err("debug approval is already armed or active".to_string());
        }
        state.lease = LeaseState::Armed {
            expires_at: now + ARMED_TTL_SECONDS,
        };
        state.signed_requests.clear();
        state.verified_requests.clear();
        self.audit("enable", "armed", None, None);
        Ok(status_from_state(&state.lease, &self.instance_nonce, now))
    }

    pub fn revoke(&self, reason: &str) -> DebugApprovalStatus {
        let now = now_epoch_seconds();
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        let previous_hash = active_lease(&state.lease).map(|lease| lease.lease_hash.as_str());
        self.audit("revoke", reason, previous_hash, None);
        state.lease = LeaseState::Disabled {
            reason: reason.to_string(),
        };
        state.signed_requests.clear();
        state.verified_requests.clear();
        status_from_state(&state.lease, &self.instance_nonce, now)
    }

    pub fn start_session(
        &self,
        request: DebugSessionStartRequest,
    ) -> Result<DebugApprovalStatus, String> {
        validate_identifier(&request.session_id, "session_id")?;
        validate_identifier(&request.run_id, "run_id")?;
        validate_identifier(&request.pack_id, "pack_id")?;
        validate_identifier(&request.profile_id, "profile_id")?;
        let process_id = request
            .process_id
            .ok_or_else(|| "debug session must be bound to a live process".to_string())?;
        if process_has_ended(process_id) {
            return Err("debug session process is not running".to_string());
        }
        let workspace = canonical_workspace(&request.workspace)?;
        let workspace_digest = sha256_text(workspace.to_string_lossy().as_bytes());
        let now = now_epoch_seconds();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        match &state.lease {
            LeaseState::Armed { expires_at } if *expires_at > now => {}
            LeaseState::Active(_) => {
                return Err("debug approval is already consumed by another session".to_string())
            }
            _ => return Err("debug approval is not armed".to_string()),
        }
        let lease_material = format!(
            "{}\n{}\n{}\n{}\n{}\n{}",
            self.instance_nonce,
            request.session_id,
            request.run_id,
            workspace_digest,
            request.pack_id,
            request.profile_id
        );
        let lease = ActiveLease {
            session_id: request.session_id,
            run_id: request.run_id,
            workspace,
            workspace_digest,
            pack_id: request.pack_id,
            profile_id: request.profile_id,
            process_id,
            expires_at: now + ACTIVE_TTL_SECONDS,
            lease_hash: sha256_text(&lease_material),
        };
        self.audit(
            "consume",
            "active",
            Some(&lease.lease_hash),
            Some(&lease.run_id),
        );
        state.lease = LeaseState::Active(lease);
        state.signed_requests.clear();
        state.verified_requests.clear();
        Ok(status_from_state(&state.lease, &self.instance_nonce, now))
    }

    pub fn stop_session(
        &self,
        request: DebugSessionStopRequest,
    ) -> Result<DebugApprovalStatus, String> {
        let state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        let active = active_lease(&state.lease)
            .ok_or_else(|| "no active debug approval session".to_string())?;
        if active.session_id != request.session_id || active.run_id != request.run_id {
            drop(state);
            self.revoke("binding_mismatch");
            return Err("debug session binding mismatch; approval was revoked".to_string());
        }
        drop(state);
        Ok(self.revoke("session_stopped"))
    }

    pub fn sign_operator(&self, request: DebugOperatorRequest) -> Result<DebugCliOperator, String> {
        validate_digest(&request.workspace_digest, "workspace_digest")?;
        validate_digest(
            &request.canonical_arguments_digest,
            "canonical_arguments_digest",
        )?;
        if let Some(target_digest) = request.target_digest.as_deref() {
            validate_digest(target_digest, "target_digest")?;
        }
        for (value, name) in [
            (&request.session_id, "session_id"),
            (&request.run_id, "run_id"),
            (&request.request_id, "request_id"),
            (&request.permission_id, "permission_id"),
            (&request.tool, "tool"),
            (&request.action, "action"),
            (&request.operation, "operation"),
            (&request.conversation_owner, "conversation_owner"),
        ] {
            validate_identifier(value, name)?;
        }

        let now = now_epoch_seconds();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        let active = active_lease(&state.lease)
            .ok_or_else(|| "no active debug approval session".to_string())?;
        if active.session_id != request.session_id
            || active.run_id != request.run_id
            || active.workspace_digest != request.workspace_digest
        {
            let lease_hash = active.lease_hash.clone();
            let run_id = active.run_id.clone();
            state.lease = LeaseState::Disabled {
                reason: "binding_mismatch".to_string(),
            };
            state.signed_requests.clear();
            state.verified_requests.clear();
            self.audit(
                "revoke",
                "binding_mismatch",
                Some(&lease_hash),
                Some(&run_id),
            );
            return Err(
                "debug session, run, or workspace binding mismatch; approval was revoked"
                    .to_string(),
            );
        }
        if request.request_expires_at <= now {
            return Err("approval request has expired".to_string());
        }
        let lease_hash = active.lease_hash.clone();
        let active_run_id = active.run_id.clone();
        if state.signed_requests.contains(&request.request_id) {
            self.audit(
                "replay",
                "operator_already_issued",
                Some(&lease_hash),
                Some(&active_run_id),
            );
            return Err("debug operator was already issued for this request".to_string());
        }

        let mut operator = DebugCliOperator {
            kind: "debug_cli_operator".to_string(),
            version: 1,
            origin: "launcher_debug_cli".to_string(),
            scope: "once".to_string(),
            session_id: request.session_id,
            run_id: request.run_id,
            workspace_digest: request.workspace_digest,
            request_id: request.request_id,
            permission_id: request.permission_id,
            tool: request.tool,
            action: request.action,
            operation: request.operation,
            canonical_arguments_digest: request.canonical_arguments_digest,
            target_digest: request.target_digest,
            conversation_owner: request.conversation_owner,
            issued_at: now,
            expires_at: request
                .request_expires_at
                .min(active.expires_at)
                .min(now + 120),
            nonce: random_identifier("approval"),
            signature: String::new(),
        };
        let unsigned = canonical_operator_payload(&operator)?;
        let mut mac = HmacSha256::new_from_slice(&self.signing_key)
            .map_err(|_| "debug signing key unavailable")?;
        mac.update(unsigned.as_bytes());
        operator.signature = hex::encode(mac.finalize().into_bytes());
        state.signed_requests.insert(operator.request_id.clone());
        self.audit(
            "operator_issued",
            "once",
            Some(&lease_hash),
            Some(&active_run_id),
        );
        Ok(operator)
    }

    pub fn verify_operator(
        &self,
        request: DebugOperatorVerifyRequest,
    ) -> Result<DebugCliOperator, String> {
        let operator = request.debug_cli_operator;
        if operator.kind != "debug_cli_operator"
            || operator.version != 1
            || operator.origin != "launcher_debug_cli"
            || operator.scope != "once"
        {
            return Err("debug operator provenance is invalid".to_string());
        }
        validate_digest(&operator.workspace_digest, "workspace_digest")?;
        validate_digest(
            &operator.canonical_arguments_digest,
            "canonical_arguments_digest",
        )?;
        if let Some(target_digest) = operator.target_digest.as_deref() {
            validate_digest(target_digest, "target_digest")?;
        }
        let now = now_epoch_seconds();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        let active = active_lease(&state.lease)
            .ok_or_else(|| "no active debug approval session".to_string())?;
        if operator.session_id != active.session_id
            || operator.run_id != active.run_id
            || operator.workspace_digest != active.workspace_digest
        {
            let lease_hash = active.lease_hash.clone();
            let run_id = active.run_id.clone();
            state.lease = LeaseState::Disabled {
                reason: "binding_mismatch".to_string(),
            };
            state.signed_requests.clear();
            state.verified_requests.clear();
            self.audit(
                "revoke",
                "binding_mismatch",
                Some(&lease_hash),
                Some(&run_id),
            );
            return Err("debug operator binding mismatch; approval was revoked".to_string());
        }
        if operator.issued_at > now
            || operator.expires_at <= now
            || operator.expires_at > active.expires_at
        {
            return Err("debug operator expired or has invalid timestamps".to_string());
        }
        if !state.signed_requests.contains(&operator.request_id) {
            return Err("debug operator was not issued by this launcher instance".to_string());
        }
        let signature = hex::decode(&operator.signature)
            .map_err(|_| "debug operator signature is invalid".to_string())?;
        let unsigned = canonical_operator_payload(&operator)?;
        let mut mac = HmacSha256::new_from_slice(&self.signing_key)
            .map_err(|_| "debug signing key unavailable")?;
        mac.update(unsigned.as_bytes());
        mac.verify_slice(&signature)
            .map_err(|_| "debug operator signature is invalid".to_string())?;
        let lease_hash = active.lease_hash.clone();
        let run_id = active.run_id.clone();
        if !state.verified_requests.insert(operator.request_id.clone()) {
            self.audit(
                "replay",
                "operator_already_verified",
                Some(&lease_hash),
                Some(&run_id),
            );
            return Err("debug operator has already been consumed".to_string());
        }
        self.audit(
            "operator_verified",
            "approved_once",
            Some(&lease_hash),
            Some(&run_id),
        );
        Ok(operator)
    }

    fn audit(&self, event: &str, result: &str, lease_hash: Option<&str>, run_id: Option<&str>) {
        let payload = json!({
            "ts": now_epoch_seconds(),
            "event": event,
            "result": result,
            "decision_source": "delegated_debug_cli",
            "instance_nonce_hash": sha256_text(&self.instance_nonce),
            "lease_hash": lease_hash,
            "run_id": run_id,
        });
        if let Some(parent) = self.audit_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let mut options = OpenOptions::new();
        options.create(true).append(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        if let Ok(mut file) = options.open(&self.audit_path) {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let _ = file.set_permissions(std::fs::Permissions::from_mode(0o600));
            }
            let _ = writeln!(file, "{payload}");
        }
    }
}

fn canonical_operator_payload(operator: &DebugCliOperator) -> Result<String, String> {
    serde_json::to_string(&json!({
        "kind": operator.kind,
        "version": operator.version,
        "origin": operator.origin,
        "scope": operator.scope,
        "session_id": operator.session_id,
        "run_id": operator.run_id,
        "workspace_digest": operator.workspace_digest,
        "request_id": operator.request_id,
        "permission_id": operator.permission_id,
        "tool": operator.tool,
        "action": operator.action,
        "operation": operator.operation,
        "canonical_arguments_digest": operator.canonical_arguments_digest,
        "target_digest": operator.target_digest,
        "conversation_owner": operator.conversation_owner,
        "issued_at": operator.issued_at,
        "expires_at": operator.expires_at,
        "nonce": operator.nonce,
    }))
    .map_err(|error| format!("failed to encode debug operator: {error}"))
}

fn status_from_state(state: &LeaseState, instance_nonce: &str, now: u64) -> DebugApprovalStatus {
    match state {
        LeaseState::Disabled { reason } => DebugApprovalStatus {
            state: "disabled".to_string(),
            reason: Some(reason.clone()),
            armed_remaining_seconds: None,
            session_id: None,
            run_id: None,
            workspace: None,
            workspace_digest: None,
            pack_id: None,
            profile_id: None,
            expires_at: None,
            instance_nonce: instance_nonce.to_string(),
        },
        LeaseState::Armed { expires_at } => DebugApprovalStatus {
            state: "armed".to_string(),
            reason: None,
            armed_remaining_seconds: Some(expires_at.saturating_sub(now)),
            session_id: None,
            run_id: None,
            workspace: None,
            workspace_digest: None,
            pack_id: None,
            profile_id: None,
            expires_at: Some(*expires_at),
            instance_nonce: instance_nonce.to_string(),
        },
        LeaseState::Active(active) => DebugApprovalStatus {
            state: "active".to_string(),
            reason: None,
            armed_remaining_seconds: None,
            session_id: Some(active.session_id.clone()),
            run_id: Some(active.run_id.clone()),
            workspace: Some(active.workspace.to_string_lossy().into_owned()),
            workspace_digest: Some(active.workspace_digest.clone()),
            pack_id: Some(active.pack_id.clone()),
            profile_id: Some(active.profile_id.clone()),
            expires_at: Some(active.expires_at),
            instance_nonce: instance_nonce.to_string(),
        },
    }
}

fn expire_if_needed(state: &mut DebugApprovalState, now: u64) {
    let expired = match &state.lease {
        LeaseState::Armed { expires_at } => *expires_at <= now,
        LeaseState::Active(active) => {
            active.expires_at <= now || process_has_ended(active.process_id)
        }
        LeaseState::Disabled { .. } => false,
    };
    if expired {
        state.lease = LeaseState::Disabled {
            reason: "expired".to_string(),
        };
        state.signed_requests.clear();
        state.verified_requests.clear();
    }
}

fn process_has_ended(process_id: u32) -> bool {
    #[cfg(unix)]
    {
        return !std::process::Command::new("/bin/kill")
            .arg("-0")
            .arg(process_id.to_string())
            .status()
            .map(|status| status.success())
            .unwrap_or(false);
    }
    #[cfg(not(unix))]
    {
        let output = crate::process_utils::command("tasklist")
            .args(["/FI", &format!("PID eq {process_id}"), "/FO", "CSV", "/NH"])
            .output();
        match output {
            Ok(output) if output.status.success() => {
                let text = String::from_utf8_lossy(&output.stdout);
                text.trim().is_empty() || text.trim_start().starts_with("INFO:")
            }
            _ => true,
        }
    }
}

fn active_lease(state: &LeaseState) -> Option<&ActiveLease> {
    match state {
        LeaseState::Active(active) => Some(active),
        _ => None,
    }
}

fn canonical_workspace(value: &str) -> Result<PathBuf, String> {
    let raw = Path::new(value);
    if !raw.is_absolute() {
        return Err("workspace must be an absolute path".to_string());
    }
    let canonical = raw
        .canonicalize()
        .map_err(|_| "workspace must exist and be canonicalizable".to_string())?;
    if !canonical.is_dir() {
        return Err("workspace must be a directory".to_string());
    }
    Ok(canonical)
}

fn validate_identifier(value: &str, name: &str) -> Result<(), String> {
    let trimmed = value.trim();
    if !(1..=512).contains(&trimmed.len()) || trimmed.chars().any(char::is_control) {
        return Err(format!("{name} is invalid"));
    }
    Ok(())
}

fn validate_digest(value: &str, name: &str) -> Result<(), String> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(format!("{name} must be a sha256 digest"));
    }
    Ok(())
}

fn random_identifier(prefix: &str) -> String {
    let suffix: String = rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect();
    format!("{prefix}-{suffix}")
}

fn sha256_text(value: impl AsRef<[u8]>) -> String {
    hex::encode(Sha256::digest(value.as_ref()))
}

fn now_epoch_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manager() -> DebugApprovalManager {
        DebugApprovalManager::new(std::env::temp_dir().join(format!(
            "tobkiri-debug-approval-test-{}.jsonl",
            random_identifier("audit")
        )))
    }

    fn start_request(workspace: &Path) -> DebugSessionStartRequest {
        DebugSessionStartRequest {
            session_id: "session-12345678".to_string(),
            run_id: "run-12345678".to_string(),
            workspace: workspace.to_string_lossy().into_owned(),
            pack_id: "defaultspack".to_string(),
            profile_id: "defaults".to_string(),
            process_id: Some(std::process::id()),
        }
    }

    #[test]
    fn starts_disabled_and_requires_explicit_arm() {
        let manager = manager();
        assert_eq!(manager.status().state, "disabled");
        assert!(manager.arm(false).is_err());
        assert_eq!(manager.status().state, "disabled");
    }

    #[test]
    fn armed_lease_is_consumed_by_exactly_one_session() {
        let manager = manager();
        let workspace = std::env::temp_dir();
        manager.arm(true).unwrap();
        assert_eq!(
            manager
                .start_session(start_request(&workspace))
                .unwrap()
                .state,
            "active"
        );
        let mut second = start_request(&workspace);
        second.session_id = "session-87654321".to_string();
        assert!(manager.start_session(second).is_err());
    }

    #[test]
    fn session_requires_a_live_process_binding() {
        let manager = manager();
        manager.arm(true).unwrap();
        let mut request = start_request(&std::env::temp_dir());
        request.process_id = None;
        assert!(manager.start_session(request).is_err());
        assert_eq!(manager.status().state, "armed");
    }

    #[test]
    fn operator_is_bound_once_to_run_workspace_and_request() {
        let manager = manager();
        let workspace = std::env::temp_dir().canonicalize().unwrap();
        manager.arm(true).unwrap();
        let status = manager.start_session(start_request(&workspace)).unwrap();
        let request = DebugOperatorRequest {
            session_id: status.session_id.clone().unwrap(),
            run_id: status.run_id.clone().unwrap(),
            workspace_digest: status.workspace_digest.clone().unwrap(),
            request_id: "apr-12345678".to_string(),
            permission_id: "computer.control".to_string(),
            tool: "computer_use".to_string(),
            action: "computer.type".to_string(),
            operation: "computer.type".to_string(),
            canonical_arguments_digest: "a".repeat(64),
            target_digest: Some("b".repeat(64)),
            conversation_owner: "conversation-1234".to_string(),
            request_expires_at: now_epoch_seconds() + 60,
        };
        let operator = manager.sign_operator(request.clone()).unwrap();
        assert_eq!(operator.kind, "debug_cli_operator");
        assert_eq!(operator.origin, "launcher_debug_cli");
        assert_eq!(operator.scope, "once");
        assert!(!operator.signature.is_empty());
        assert!(manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator,
            })
            .is_ok());
        assert!(manager.sign_operator(request).is_err());
    }

    #[test]
    fn tampered_and_replayed_operators_fail_closed() {
        let manager = manager();
        let workspace = std::env::temp_dir().canonicalize().unwrap();
        manager.arm(true).unwrap();
        let status = manager.start_session(start_request(&workspace)).unwrap();
        let request = DebugOperatorRequest {
            session_id: status.session_id.unwrap(),
            run_id: status.run_id.unwrap(),
            workspace_digest: status.workspace_digest.unwrap(),
            request_id: "apr-tamper-1234".to_string(),
            permission_id: "computer.control".to_string(),
            tool: "computer_use".to_string(),
            action: "computer.click".to_string(),
            operation: "computer.click".to_string(),
            canonical_arguments_digest: "c".repeat(64),
            target_digest: None,
            conversation_owner: "conversation-1234".to_string(),
            request_expires_at: now_epoch_seconds() + 60,
        };
        let operator = manager.sign_operator(request).unwrap();
        let mut tampered = operator.clone();
        tampered.action = "computer.type".to_string();
        assert!(manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: tampered,
            })
            .is_err());
        assert!(manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator.clone(),
            })
            .is_ok());
        assert!(manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator,
            })
            .is_err());
    }

    #[test]
    fn revoke_invalidates_active_session() {
        let manager = manager();
        manager.arm(true).unwrap();
        manager
            .start_session(start_request(&std::env::temp_dir()))
            .unwrap();
        assert_eq!(manager.revoke("user_revoked").state, "disabled");
    }
}
