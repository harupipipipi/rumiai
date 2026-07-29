use std::collections::{HashMap, HashSet};
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use hmac::{Hmac, Mac};
use rand::{distributions::Alphanumeric, Rng, RngCore};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};

type HmacSha256 = Hmac<Sha256>;

const REQUEST_TTL: Duration = Duration::from_secs(5 * 60);
const ACTIVE_TTL: Duration = Duration::from_secs(30 * 60);
const OPERATOR_TTL_SECONDS: u64 = 120;

#[derive(Debug, Clone)]
enum LeaseState {
    Disabled { reason: String },
    Pending(PendingSession),
    Armed(PendingSession),
    Active(ActiveLease),
}

#[derive(Debug, Clone)]
struct PendingSession {
    session_id: String,
    run_id: String,
    workspace: PathBuf,
    workspace_digest: String,
    pack_id: String,
    profile_id: String,
    process_id: u32,
    process_fingerprint: String,
    claim_secret_hash: String,
    expires_at: u64,
    deadline: Instant,
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
    process_fingerprint: String,
    session_secret_hash: String,
    lease_epoch: u64,
    expires_at: u64,
    deadline: Instant,
    lease_hash: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OperatorState {
    Issued,
    Settling,
    Settled,
    ResumeFailed,
    ExecutionConsumed,
}

#[derive(Debug, Clone)]
struct OperatorRecord {
    operator: DebugCliOperator,
    state: OperatorState,
    execution_jti: Option<String>,
}

#[derive(Debug)]
struct DebugApprovalState {
    lease: LeaseState,
    next_lease_epoch: u64,
    operators: HashMap<String, OperatorRecord>,
    consumed_execution_jtis: HashSet<String>,
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
    pub process_id: Option<u32>,
    pub lease_epoch: Option<u64>,
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
    pub process_id: u32,
    pub claim_secret: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct DebugSessionStartResponse {
    pub status: DebugApprovalStatus,
    pub session_secret: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugSessionStopRequest {
    pub session_id: String,
    pub run_id: String,
    pub session_secret: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugOperatorRequest {
    pub session_id: String,
    pub run_id: String,
    pub workspace_digest: String,
    pub pack_id: String,
    pub profile_id: String,
    pub lease_epoch: u64,
    pub session_secret: String,
    pub request_id: String,
    pub permission_id: String,
    pub tool: String,
    pub action: String,
    pub operation: String,
    pub decision: String,
    pub canonical_arguments_digest: String,
    #[serde(default)]
    pub target_digest: Option<String>,
    pub conversation_id: String,
    pub operation_owner: String,
    pub request_expires_at: u64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugOperatorVerifyRequest {
    pub debug_cli_operator: DebugCliOperator,
    pub expected_decision: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugOperatorSettleRequest {
    pub debug_cli_operator: DebugCliOperator,
    pub outcome: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebugExecutionConsumeRequest {
    pub request_id: String,
    pub lease_epoch: u64,
    pub execution_jti: String,
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
    pub pack_id: String,
    pub profile_id: String,
    pub lease_epoch: u64,
    pub request_id: String,
    pub permission_id: String,
    pub tool: String,
    pub action: String,
    pub operation: String,
    pub decision: String,
    pub canonical_arguments_digest: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_digest: Option<String>,
    pub conversation_id: String,
    pub operation_owner: String,
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
                next_lease_epoch: 1,
                operators: HashMap::new(),
                consumed_execution_jtis: HashSet::new(),
            }),
            instance_nonce: random_identifier("launcher"),
            signing_key,
            audit_path,
        }
    }

    pub fn status(&self) -> DebugApprovalStatus {
        let now_epoch = now_epoch_seconds();
        let now = Instant::now();
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        expire_if_needed(&mut state, now);
        status_from_state(&state.lease, &self.instance_nonce, now_epoch, now)
    }

    pub fn register_session(
        &self,
        request: DebugSessionStartRequest,
    ) -> Result<DebugApprovalStatus, String> {
        let pending = pending_from_request(&request)?;
        let now_epoch = now_epoch_seconds();
        let now = Instant::now();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        match &state.lease {
            LeaseState::Disabled { .. } => {}
            LeaseState::Pending(existing)
                if existing.session_id == pending.session_id
                    && existing.claim_secret_hash == pending.claim_secret_hash =>
            {
                return Ok(status_from_state(
                    &state.lease,
                    &self.instance_nonce,
                    now_epoch,
                    now,
                ));
            }
            _ => return Err("another debug session request is already pending or active".into()),
        }
        self.audit(
            "session_requested",
            "pending_human_confirmation",
            None,
            Some(&pending.run_id),
            None,
        )?;
        state.lease = LeaseState::Pending(pending);
        state.operators.clear();
        Ok(status_from_state(
            &state.lease,
            &self.instance_nonce,
            now_epoch,
            now,
        ))
    }

    /// Called only after the Tauri command has validated the dedicated Launcher
    /// window and completed a native operating-system confirmation dialog.
    pub fn arm(&self) -> Result<DebugApprovalStatus, String> {
        let now_epoch = now_epoch_seconds();
        let now = Instant::now();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        let pending = match &state.lease {
            LeaseState::Pending(pending) => pending.clone(),
            _ => return Err("a CLI debug session must be requested before enabling".into()),
        };
        self.audit(
            "enable",
            "armed_exact_session",
            None,
            Some(&pending.run_id),
            None,
        )?;
        state.lease = LeaseState::Armed(pending);
        Ok(status_from_state(
            &state.lease,
            &self.instance_nonce,
            now_epoch,
            now,
        ))
    }

    pub fn revoke(&self, reason: &str) -> Result<DebugApprovalStatus, String> {
        let now_epoch = now_epoch_seconds();
        let now = Instant::now();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        let (lease_hash, run_id, lease_epoch) = match active_lease(&state.lease) {
            Some(active) => (
                Some(active.lease_hash.clone()),
                Some(active.run_id.clone()),
                Some(active.lease_epoch),
            ),
            None => (None, None, None),
        };
        self.audit(
            "revoke",
            reason,
            lease_hash.as_deref(),
            run_id.as_deref(),
            lease_epoch,
        )?;
        state.lease = LeaseState::Disabled {
            reason: reason.to_string(),
        };
        state.operators.clear();
        state.consumed_execution_jtis.clear();
        Ok(status_from_state(
            &state.lease,
            &self.instance_nonce,
            now_epoch,
            now,
        ))
    }

    pub fn start_session(
        &self,
        request: DebugSessionStartRequest,
    ) -> Result<DebugSessionStartResponse, String> {
        let candidate = pending_from_request(&request)?;
        let now_epoch = now_epoch_seconds();
        let now = Instant::now();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        let approved = match &state.lease {
            LeaseState::Armed(pending) => pending.clone(),
            LeaseState::Active(_) => return Err("debug approval is already active".into()),
            _ => return Err("exact debug session has not been confirmed in Launcher".into()),
        };
        if !pending_matches(&approved, &candidate) {
            return Err("debug session claim does not match the Launcher-confirmed request".into());
        }
        let current_fingerprint = process_fingerprint(candidate.process_id)?;
        if current_fingerprint != approved.process_fingerprint {
            return Err("debug guardian process identity changed before claim".into());
        }
        let session_secret = random_identifier("debug-session-secret");
        let lease_epoch = state.next_lease_epoch;
        state.next_lease_epoch = state.next_lease_epoch.saturating_add(1);
        let lease_material = format!(
            "{}\n{}\n{}\n{}\n{}\n{}\n{}",
            self.instance_nonce,
            candidate.session_id,
            candidate.run_id,
            candidate.workspace_digest,
            candidate.pack_id,
            candidate.profile_id,
            lease_epoch,
        );
        let lease = ActiveLease {
            session_id: candidate.session_id,
            run_id: candidate.run_id,
            workspace: candidate.workspace,
            workspace_digest: candidate.workspace_digest,
            pack_id: candidate.pack_id,
            profile_id: candidate.profile_id,
            process_id: candidate.process_id,
            process_fingerprint: current_fingerprint,
            session_secret_hash: sha256_text(&session_secret),
            lease_epoch,
            expires_at: now_epoch + ACTIVE_TTL.as_secs(),
            deadline: now + ACTIVE_TTL,
            lease_hash: sha256_text(lease_material),
        };
        self.audit(
            "claim",
            "active",
            Some(&lease.lease_hash),
            Some(&lease.run_id),
            Some(lease.lease_epoch),
        )?;
        state.lease = LeaseState::Active(lease);
        state.operators.clear();
        let status = status_from_state(&state.lease, &self.instance_nonce, now_epoch, now);
        Ok(DebugSessionStartResponse {
            status,
            session_secret,
        })
    }

    pub fn stop_session(
        &self,
        request: DebugSessionStopRequest,
    ) -> Result<DebugApprovalStatus, String> {
        self.require_active_secret(
            &request.session_id,
            &request.run_id,
            &request.session_secret,
        )?;
        self.revoke("session_stopped")
    }

    pub fn sign_operator(&self, request: DebugOperatorRequest) -> Result<DebugCliOperator, String> {
        validate_operator_request(&request)?;
        let now_epoch = now_epoch_seconds();
        let now = Instant::now();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, now);
        let active = active_lease(&state.lease)
            .ok_or_else(|| "no active debug approval session".to_string())?
            .clone();
        require_secret(&active, &request.session_secret)?;
        if active.session_id != request.session_id
            || active.run_id != request.run_id
            || active.workspace_digest != request.workspace_digest
            || active.pack_id != request.pack_id
            || active.profile_id != request.profile_id
            || active.lease_epoch != request.lease_epoch
        {
            return Err("debug request does not match the active session binding".into());
        }
        if request.request_expires_at <= now_epoch {
            return Err("approval request has expired".into());
        }
        if let Some(existing) = state.operators.get(&request.request_id) {
            let proposed = operator_from_request(
                &request,
                now_epoch,
                existing.operator.issued_at,
                existing.operator.expires_at,
                existing.operator.nonce.clone(),
            );
            if canonical_operator_payload(&proposed)?
                == canonical_operator_payload(&existing.operator)?
            {
                return Ok(existing.operator.clone());
            }
            return Err("request already has a differently-bound debug operator".into());
        }
        let expires_at = request
            .request_expires_at
            .min(active.expires_at)
            .min(now_epoch + OPERATOR_TTL_SECONDS);
        let mut operator = operator_from_request(
            &request,
            now_epoch,
            now_epoch,
            expires_at,
            random_identifier("approval"),
        );
        operator.signature = self.sign(&operator)?;
        self.audit(
            "operator_issued",
            &operator.decision,
            Some(&active.lease_hash),
            Some(&active.run_id),
            Some(active.lease_epoch),
        )?;
        state.operators.insert(
            operator.request_id.clone(),
            OperatorRecord {
                operator: operator.clone(),
                state: OperatorState::Issued,
                execution_jti: None,
            },
        );
        Ok(operator)
    }

    pub fn verify_operator(
        &self,
        request: DebugOperatorVerifyRequest,
    ) -> Result<DebugCliOperator, String> {
        let operator = request.debug_cli_operator;
        validate_decision(&request.expected_decision)?;
        if operator.decision != request.expected_decision {
            return Err("debug operator decision does not match this endpoint".into());
        }
        self.verify_signature_and_active_binding(&operator)?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        let active = active_lease(&state.lease)
            .ok_or_else(|| "no active debug approval session".to_string())?
            .clone();
        let record = state
            .operators
            .get_mut(&operator.request_id)
            .ok_or_else(|| "debug operator was not issued by this Launcher".to_string())?;
        if record.operator != operator {
            return Err("debug operator differs from the issued operator".into());
        }
        match record.state {
            OperatorState::Issued | OperatorState::Settling | OperatorState::ResumeFailed => {
                self.audit(
                    "operator_verified",
                    "settling_idempotent",
                    Some(&active.lease_hash),
                    Some(&active.run_id),
                    Some(active.lease_epoch),
                )?;
                record.state = OperatorState::Settling;
                Ok(operator)
            }
            OperatorState::Settled => Ok(operator),
            OperatorState::ExecutionConsumed => Err("debug operator execution was consumed".into()),
        }
    }

    pub fn settle_operator(
        &self,
        request: DebugOperatorSettleRequest,
    ) -> Result<DebugCliOperator, String> {
        self.verify_signature_and_active_binding(&request.debug_cli_operator)?;
        let next = match request.outcome.as_str() {
            "settled" => OperatorState::Settled,
            "resume_failed" => OperatorState::ResumeFailed,
            _ => return Err("invalid debug operator settlement outcome".into()),
        };
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        let active = active_lease(&state.lease)
            .ok_or_else(|| "no active debug approval session".to_string())?
            .clone();
        let record = state
            .operators
            .get_mut(&request.debug_cli_operator.request_id)
            .ok_or_else(|| "debug operator was not issued by this Launcher".to_string())?;
        if record.operator != request.debug_cli_operator {
            return Err("debug operator differs from the issued operator".into());
        }
        match (record.state, next) {
            (OperatorState::Settling, _) => {}
            (OperatorState::Settled, OperatorState::Settled)
            | (OperatorState::ResumeFailed, OperatorState::ResumeFailed) => {
                return Ok(record.operator.clone());
            }
            (OperatorState::ExecutionConsumed, _) => {
                return Err("debug operator execution was already consumed".into());
            }
            _ => return Err("debug operator is not ready for settlement".into()),
        }
        self.audit(
            "operator_settlement",
            request.outcome.as_str(),
            Some(&active.lease_hash),
            Some(&active.run_id),
            Some(active.lease_epoch),
        )?;
        record.state = next;
        Ok(record.operator.clone())
    }

    pub fn consume_execution(&self, request: DebugExecutionConsumeRequest) -> Result<(), String> {
        validate_identifier(&request.execution_jti, "execution_jti")?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, Instant::now());
        let active = active_lease(&state.lease)
            .ok_or_else(|| "debug approval was revoked or expired".to_string())?
            .clone();
        if active.lease_epoch != request.lease_epoch {
            return Err("debug execution lease was revoked".into());
        }
        if state
            .consumed_execution_jtis
            .contains(&request.execution_jti)
        {
            let record = state
                .operators
                .get(&request.request_id)
                .ok_or_else(|| "debug execution has no active operator".to_string())?;
            if record.execution_jti.as_deref() == Some(request.execution_jti.as_str())
                && record.state == OperatorState::ExecutionConsumed
            {
                return Ok(());
            }
            return Err("debug execution token has already been consumed".into());
        }
        let record = state
            .operators
            .get_mut(&request.request_id)
            .ok_or_else(|| "debug execution has no active operator".to_string())?;
        if record.operator.lease_epoch != request.lease_epoch
            || record.operator.decision != "approve"
        {
            return Err("debug execution binding mismatch".into());
        }
        if record.state != OperatorState::Settled {
            return Err("debug approval has not settled".into());
        }
        self.audit(
            "execution_consumed",
            "once",
            Some(&active.lease_hash),
            Some(&active.run_id),
            Some(active.lease_epoch),
        )?;
        record.state = OperatorState::ExecutionConsumed;
        record.execution_jti = Some(request.execution_jti.clone());
        state.consumed_execution_jtis.insert(request.execution_jti);
        Ok(())
    }

    fn require_active_secret(
        &self,
        session_id: &str,
        run_id: &str,
        secret: &str,
    ) -> Result<(), String> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, Instant::now());
        let active = active_lease(&state.lease)
            .ok_or_else(|| "no active debug approval session".to_string())?;
        if active.session_id != session_id || active.run_id != run_id {
            return Err("debug session binding mismatch".into());
        }
        require_secret(active, secret)
    }

    fn verify_signature_and_active_binding(
        &self,
        operator: &DebugCliOperator,
    ) -> Result<(), String> {
        validate_operator(operator)?;
        let signature =
            hex::decode(&operator.signature).map_err(|_| "debug operator signature is invalid")?;
        let unsigned = canonical_operator_payload(operator)?;
        let mut mac = HmacSha256::new_from_slice(&self.signing_key)
            .map_err(|_| "debug signing key unavailable")?;
        mac.update(unsigned.as_bytes());
        mac.verify_slice(&signature)
            .map_err(|_| "debug operator signature is invalid".to_string())?;
        let now_epoch = now_epoch_seconds();
        let mut state = self
            .state
            .lock()
            .map_err(|_| "debug approval state unavailable")?;
        expire_if_needed(&mut state, Instant::now());
        let active = active_lease(&state.lease)
            .ok_or_else(|| "debug approval was revoked or expired".to_string())?;
        if operator.session_id != active.session_id
            || operator.run_id != active.run_id
            || operator.workspace_digest != active.workspace_digest
            || operator.pack_id != active.pack_id
            || operator.profile_id != active.profile_id
            || operator.lease_epoch != active.lease_epoch
        {
            return Err("debug operator active lease binding mismatch".into());
        }
        if operator.issued_at > now_epoch
            || operator.expires_at <= now_epoch
            || operator.expires_at > active.expires_at
        {
            return Err("debug operator expired or has invalid timestamps".into());
        }
        Ok(())
    }

    fn sign(&self, operator: &DebugCliOperator) -> Result<String, String> {
        let unsigned = canonical_operator_payload(operator)?;
        let mut mac = HmacSha256::new_from_slice(&self.signing_key)
            .map_err(|_| "debug signing key unavailable")?;
        mac.update(unsigned.as_bytes());
        Ok(hex::encode(mac.finalize().into_bytes()))
    }

    fn audit(
        &self,
        event: &str,
        result: &str,
        lease_hash: Option<&str>,
        run_id: Option<&str>,
        lease_epoch: Option<u64>,
    ) -> Result<(), String> {
        let payload = json!({
            "ts": now_epoch_seconds(),
            "event": event,
            "result": result,
            "decision_source": "delegated_debug_cli",
            "instance_nonce_hash": sha256_text(&self.instance_nonce),
            "lease_hash": lease_hash,
            "lease_epoch": lease_epoch,
            "run_id": run_id,
        });
        if let Some(parent) = self.audit_path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|error| format!("debug approval audit directory unavailable: {error}"))?;
        }
        let mut options = OpenOptions::new();
        options.create(true).append(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options
            .open(&self.audit_path)
            .map_err(|error| format!("debug approval audit unavailable: {error}"))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(std::fs::Permissions::from_mode(0o600))
                .map_err(|error| format!("debug approval audit permissions failed: {error}"))?;
        }
        writeln!(file, "{payload}")
            .map_err(|error| format!("debug approval audit write failed: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("debug approval audit fsync failed: {error}"))
    }
}

fn pending_from_request(request: &DebugSessionStartRequest) -> Result<PendingSession, String> {
    for (value, name) in [
        (&request.session_id, "session_id"),
        (&request.run_id, "run_id"),
        (&request.pack_id, "pack_id"),
        (&request.profile_id, "profile_id"),
    ] {
        validate_identifier(value, name)?;
    }
    if request.claim_secret.len() < 32 {
        return Err("debug session claim secret is invalid".into());
    }
    let workspace = canonical_workspace(&request.workspace)?;
    let process_fingerprint = process_fingerprint(request.process_id)?;
    let now = Instant::now();
    Ok(PendingSession {
        session_id: request.session_id.clone(),
        run_id: request.run_id.clone(),
        workspace_digest: sha256_text(workspace.to_string_lossy().as_bytes()),
        workspace,
        pack_id: request.pack_id.clone(),
        profile_id: request.profile_id.clone(),
        process_id: request.process_id,
        process_fingerprint,
        claim_secret_hash: sha256_text(&request.claim_secret),
        expires_at: now_epoch_seconds() + REQUEST_TTL.as_secs(),
        deadline: now + REQUEST_TTL,
    })
}

fn pending_matches(left: &PendingSession, right: &PendingSession) -> bool {
    left.session_id == right.session_id
        && left.run_id == right.run_id
        && left.workspace == right.workspace
        && left.workspace_digest == right.workspace_digest
        && left.pack_id == right.pack_id
        && left.profile_id == right.profile_id
        && left.process_id == right.process_id
        && left.process_fingerprint == right.process_fingerprint
        && left.claim_secret_hash == right.claim_secret_hash
}

fn operator_from_request(
    request: &DebugOperatorRequest,
    _now: u64,
    issued_at: u64,
    expires_at: u64,
    nonce: String,
) -> DebugCliOperator {
    DebugCliOperator {
        kind: "debug_cli_operator".into(),
        version: 2,
        origin: "launcher_debug_cli".into(),
        scope: "once".into(),
        session_id: request.session_id.clone(),
        run_id: request.run_id.clone(),
        workspace_digest: request.workspace_digest.clone(),
        pack_id: request.pack_id.clone(),
        profile_id: request.profile_id.clone(),
        lease_epoch: request.lease_epoch,
        request_id: request.request_id.clone(),
        permission_id: request.permission_id.clone(),
        tool: request.tool.clone(),
        action: request.action.clone(),
        operation: request.operation.clone(),
        decision: request.decision.clone(),
        canonical_arguments_digest: request.canonical_arguments_digest.clone(),
        target_digest: request.target_digest.clone(),
        conversation_id: request.conversation_id.clone(),
        operation_owner: request.operation_owner.clone(),
        issued_at,
        expires_at,
        nonce,
        signature: String::new(),
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
        "pack_id": operator.pack_id,
        "profile_id": operator.profile_id,
        "lease_epoch": operator.lease_epoch,
        "request_id": operator.request_id,
        "permission_id": operator.permission_id,
        "tool": operator.tool,
        "action": operator.action,
        "operation": operator.operation,
        "decision": operator.decision,
        "canonical_arguments_digest": operator.canonical_arguments_digest,
        "target_digest": operator.target_digest,
        "conversation_id": operator.conversation_id,
        "operation_owner": operator.operation_owner,
        "issued_at": operator.issued_at,
        "expires_at": operator.expires_at,
        "nonce": operator.nonce,
    }))
    .map_err(|error| format!("failed to encode debug operator: {error}"))
}

fn status_from_state(
    state: &LeaseState,
    instance_nonce: &str,
    now_epoch: u64,
    now: Instant,
) -> DebugApprovalStatus {
    let base = |state: &str, reason: Option<String>| DebugApprovalStatus {
        state: state.to_string(),
        reason,
        armed_remaining_seconds: None,
        session_id: None,
        run_id: None,
        workspace: None,
        workspace_digest: None,
        pack_id: None,
        profile_id: None,
        process_id: None,
        lease_epoch: None,
        expires_at: None,
        instance_nonce: instance_nonce.to_string(),
    };
    match state {
        LeaseState::Disabled { reason } => base("disabled", Some(reason.clone())),
        LeaseState::Pending(pending) | LeaseState::Armed(pending) => {
            let mut status = base(
                if matches!(state, LeaseState::Armed(_)) {
                    "armed"
                } else {
                    "pending"
                },
                None,
            );
            status.armed_remaining_seconds =
                Some(pending.deadline.saturating_duration_since(now).as_secs());
            status.session_id = Some(pending.session_id.clone());
            status.run_id = Some(pending.run_id.clone());
            status.workspace = Some(pending.workspace.to_string_lossy().into_owned());
            status.workspace_digest = Some(pending.workspace_digest.clone());
            status.pack_id = Some(pending.pack_id.clone());
            status.profile_id = Some(pending.profile_id.clone());
            status.process_id = Some(pending.process_id);
            status.expires_at = Some(pending.expires_at.max(now_epoch));
            status
        }
        LeaseState::Active(active) => {
            let mut status = base("active", None);
            status.session_id = Some(active.session_id.clone());
            status.run_id = Some(active.run_id.clone());
            status.workspace = Some(active.workspace.to_string_lossy().into_owned());
            status.workspace_digest = Some(active.workspace_digest.clone());
            status.pack_id = Some(active.pack_id.clone());
            status.profile_id = Some(active.profile_id.clone());
            status.process_id = Some(active.process_id);
            status.lease_epoch = Some(active.lease_epoch);
            status.expires_at = Some(active.expires_at);
            status
        }
    }
}

fn expire_if_needed(state: &mut DebugApprovalState, now: Instant) {
    let expired = match &state.lease {
        LeaseState::Pending(pending) | LeaseState::Armed(pending) => pending.deadline <= now,
        LeaseState::Active(active) => {
            active.deadline <= now
                || process_fingerprint(active.process_id)
                    .map(|fingerprint| fingerprint != active.process_fingerprint)
                    .unwrap_or(true)
        }
        LeaseState::Disabled { .. } => false,
    };
    if expired {
        state.lease = LeaseState::Disabled {
            reason: "expired_or_guardian_changed".into(),
        };
        state.operators.clear();
        state.consumed_execution_jtis.clear();
    }
}

fn active_lease(state: &LeaseState) -> Option<&ActiveLease> {
    match state {
        LeaseState::Active(active) => Some(active),
        _ => None,
    }
}

fn require_secret(active: &ActiveLease, supplied: &str) -> Result<(), String> {
    let supplied_hash = sha256_text(supplied);
    if supplied.len() < 32 || !constant_time_equal(&supplied_hash, &active.session_secret_hash) {
        return Err("debug session secret is invalid".into());
    }
    Ok(())
}

fn validate_operator_request(request: &DebugOperatorRequest) -> Result<(), String> {
    validate_digest(&request.workspace_digest, "workspace_digest")?;
    validate_digest(
        &request.canonical_arguments_digest,
        "canonical_arguments_digest",
    )?;
    if let Some(target_digest) = request.target_digest.as_deref() {
        validate_digest(target_digest, "target_digest")?;
    }
    validate_decision(&request.decision)?;
    for (value, name) in [
        (&request.session_id, "session_id"),
        (&request.run_id, "run_id"),
        (&request.pack_id, "pack_id"),
        (&request.profile_id, "profile_id"),
        (&request.request_id, "request_id"),
        (&request.permission_id, "permission_id"),
        (&request.tool, "tool"),
        (&request.action, "action"),
        (&request.operation, "operation"),
        (&request.conversation_id, "conversation_id"),
        (&request.operation_owner, "operation_owner"),
    ] {
        validate_identifier(value, name)?;
    }
    Ok(())
}

fn validate_operator(operator: &DebugCliOperator) -> Result<(), String> {
    if operator.kind != "debug_cli_operator"
        || operator.version != 2
        || operator.origin != "launcher_debug_cli"
        || operator.scope != "once"
    {
        return Err("debug operator provenance is invalid".into());
    }
    validate_digest(&operator.workspace_digest, "workspace_digest")?;
    validate_digest(
        &operator.canonical_arguments_digest,
        "canonical_arguments_digest",
    )?;
    if let Some(target_digest) = operator.target_digest.as_deref() {
        validate_digest(target_digest, "target_digest")?;
    }
    validate_decision(&operator.decision)
}

fn validate_decision(decision: &str) -> Result<(), String> {
    if matches!(decision, "approve" | "deny") {
        Ok(())
    } else {
        Err("debug decision must be approve or deny".into())
    }
}

fn process_fingerprint(process_id: u32) -> Result<String, String> {
    if process_id == 0 {
        return Err("debug guardian process id is invalid".into());
    }
    #[cfg(unix)]
    {
        let output = std::process::Command::new("/bin/ps")
            .args([
                "-p",
                &process_id.to_string(),
                "-o",
                "uid=",
                "-o",
                "lstart=",
                "-o",
                "comm=",
            ])
            .output()
            .map_err(|_| "failed to inspect debug guardian process")?;
        if !output.status.success() {
            return Err("debug guardian process is not running".into());
        }
        let facts = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if facts.is_empty() {
            return Err("debug guardian process identity is unavailable".into());
        }
        return Ok(sha256_text(facts));
    }
    #[cfg(not(unix))]
    {
        let output = crate::process_utils::command("tasklist")
            .args(["/FI", &format!("PID eq {process_id}"), "/FO", "CSV", "/NH"])
            .output()
            .map_err(|_| "failed to inspect debug guardian process")?;
        let facts = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !output.status.success() || facts.is_empty() || facts.starts_with("INFO:") {
            return Err("debug guardian process is not running".into());
        }
        Ok(sha256_text(facts))
    }
}

fn canonical_workspace(value: &str) -> Result<PathBuf, String> {
    let raw = Path::new(value);
    if !raw.is_absolute() {
        return Err("workspace must be an absolute path".into());
    }
    let canonical = raw
        .canonicalize()
        .map_err(|_| "workspace must exist and be canonicalizable".to_string())?;
    if !canonical.is_dir() {
        return Err("workspace must be a directory".into());
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

fn constant_time_equal(left: &str, right: &str) -> bool {
    left.len() == right.len()
        && left
            .bytes()
            .zip(right.bytes())
            .fold(0_u8, |difference, (a, b)| difference | (a ^ b))
            == 0
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
    use std::sync::Arc;

    fn manager() -> DebugApprovalManager {
        DebugApprovalManager::new(std::env::temp_dir().join(format!(
            "tobkiri-debug-approval-test-{}.jsonl",
            random_identifier("audit")
        )))
    }

    fn request(workspace: &Path) -> DebugSessionStartRequest {
        DebugSessionStartRequest {
            session_id: "session-12345678".into(),
            run_id: "run-12345678".into(),
            workspace: workspace.to_string_lossy().into_owned(),
            pack_id: "defaultspack".into(),
            profile_id: "defaults".into(),
            process_id: std::process::id(),
            claim_secret: "claim-secret-which-is-at-least-thirty-two-bytes".into(),
        }
    }

    fn active(manager: &DebugApprovalManager) -> (DebugApprovalStatus, String) {
        let request = request(&std::env::temp_dir());
        manager.register_session(request.clone()).unwrap();
        manager.arm().unwrap();
        let result = manager.start_session(request).unwrap();
        (result.status, result.session_secret)
    }

    fn operator_request(
        status: &DebugApprovalStatus,
        session_secret: &str,
        decision: &str,
    ) -> DebugOperatorRequest {
        DebugOperatorRequest {
            session_id: status.session_id.clone().unwrap(),
            run_id: status.run_id.clone().unwrap(),
            workspace_digest: status.workspace_digest.clone().unwrap(),
            pack_id: status.pack_id.clone().unwrap(),
            profile_id: status.profile_id.clone().unwrap(),
            lease_epoch: status.lease_epoch.unwrap(),
            session_secret: session_secret.into(),
            request_id: "apr-12345678".into(),
            permission_id: "computer.control".into(),
            tool: "computer_use".into(),
            action: "computer.type".into(),
            operation: "computer.type".into(),
            decision: decision.into(),
            canonical_arguments_digest: "a".repeat(64),
            target_digest: Some("b".repeat(64)),
            conversation_id: "conversation-1234".into(),
            operation_owner: "defaultspack".into(),
            request_expires_at: now_epoch_seconds() + 60,
        }
    }

    #[test]
    fn requires_registered_exact_session_before_native_arm() {
        let manager = manager();
        assert_eq!(manager.status().state, "disabled");
        assert!(manager.arm().is_err());
        let request = request(&std::env::temp_dir());
        assert_eq!(manager.register_session(request).unwrap().state, "pending");
    }

    #[test]
    fn general_broker_credential_cannot_claim_or_sign() {
        let manager = manager();
        let mut request = request(&std::env::temp_dir());
        manager.register_session(request.clone()).unwrap();
        manager.arm().unwrap();
        request.claim_secret = "wrong-claim-secret-that-is-at-least-thirty-two".into();
        assert!(manager.start_session(request).is_err());
        let second_manager = DebugApprovalManager::new(std::env::temp_dir().join(format!(
            "tobkiri-debug-approval-test-{}.jsonl",
            random_identifier("audit")
        )));
        let (status, secret) = active(&second_manager);
        let mut operator = operator_request(&status, &secret, "approve");
        operator.session_secret = "not-the-session-secret-at-all-xxxxxxxx".into();
        assert!(second_manager.sign_operator(operator).is_err());
    }

    #[test]
    fn operator_is_bound_to_decision_and_full_lease() {
        let manager = manager();
        let (status, secret) = active(&manager);
        let request = operator_request(&status, &secret, "approve");
        let operator = manager.sign_operator(request.clone()).unwrap();
        assert_eq!(operator.version, 2);
        assert_eq!(operator.decision, "approve");
        assert_eq!(operator.pack_id, "defaultspack");
        assert!(manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator.clone(),
                expected_decision: "deny".into(),
            })
            .is_err());
        assert!(manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator.clone(),
                expected_decision: "approve".into(),
            })
            .is_ok());
        assert_eq!(manager.sign_operator(request).unwrap(), operator);
    }

    #[test]
    fn revoke_invalidates_settled_but_unconsumed_execution() {
        let manager = manager();
        let (status, secret) = active(&manager);
        let operator = manager
            .sign_operator(operator_request(&status, &secret, "approve"))
            .unwrap();
        manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator.clone(),
                expected_decision: "approve".into(),
            })
            .unwrap();
        manager
            .settle_operator(DebugOperatorSettleRequest {
                debug_cli_operator: operator.clone(),
                outcome: "settled".into(),
            })
            .unwrap();
        manager.revoke("user_revoked").unwrap();
        assert!(manager
            .consume_execution(DebugExecutionConsumeRequest {
                request_id: operator.request_id,
                lease_epoch: operator.lease_epoch,
                execution_jti: "tok-12345678".into(),
            })
            .is_err());
    }

    #[test]
    fn settlement_cannot_reopen_consumed_operator() {
        let manager = manager();
        let (status, secret) = active(&manager);
        let operator = manager
            .sign_operator(operator_request(&status, &secret, "approve"))
            .unwrap();
        manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator.clone(),
                expected_decision: "approve".into(),
            })
            .unwrap();
        manager
            .settle_operator(DebugOperatorSettleRequest {
                debug_cli_operator: operator.clone(),
                outcome: "settled".into(),
            })
            .unwrap();
        manager
            .consume_execution(DebugExecutionConsumeRequest {
                request_id: operator.request_id.clone(),
                lease_epoch: operator.lease_epoch,
                execution_jti: "tok-first-execution".into(),
            })
            .unwrap();

        assert!(manager
            .settle_operator(DebugOperatorSettleRequest {
                debug_cli_operator: operator.clone(),
                outcome: "resume_failed".into(),
            })
            .is_err());
        assert!(manager
            .consume_execution(DebugExecutionConsumeRequest {
                request_id: operator.request_id,
                lease_epoch: operator.lease_epoch,
                execution_jti: "tok-second-execution".into(),
            })
            .is_err());
    }

    #[test]
    fn concurrent_execution_tokens_have_exactly_one_winner() {
        let manager = Arc::new(manager());
        let (status, secret) = active(&manager);
        let operator = manager
            .sign_operator(operator_request(&status, &secret, "approve"))
            .unwrap();
        manager
            .verify_operator(DebugOperatorVerifyRequest {
                debug_cli_operator: operator.clone(),
                expected_decision: "approve".into(),
            })
            .unwrap();
        manager
            .settle_operator(DebugOperatorSettleRequest {
                debug_cli_operator: operator.clone(),
                outcome: "settled".into(),
            })
            .unwrap();

        let attempts = ["tok-concurrent-one", "tok-concurrent-two"]
            .into_iter()
            .map(|execution_jti| {
                let manager = Arc::clone(&manager);
                let request_id = operator.request_id.clone();
                let lease_epoch = operator.lease_epoch;
                std::thread::spawn(move || {
                    manager.consume_execution(DebugExecutionConsumeRequest {
                        request_id,
                        lease_epoch,
                        execution_jti: execution_jti.into(),
                    })
                })
            })
            .collect::<Vec<_>>();
        let successes = attempts
            .into_iter()
            .map(|attempt| attempt.join().unwrap())
            .filter(Result::is_ok)
            .count();
        assert_eq!(successes, 1);
    }

    #[test]
    fn audit_failure_blocks_authority_transition() {
        let manager = DebugApprovalManager::new(PathBuf::from("/dev/null/audit.jsonl"));
        let request = request(&std::env::temp_dir());
        assert!(manager.register_session(request).is_err());
        assert_eq!(manager.status().state, "disabled");
    }
}
