use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::process::{ExitStatus, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, bail, Context, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use log::{error, warn};
use rand::{distributions::Alphanumeric, Rng};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::config::AppConfig;
use crate::desktop_system_info;
use crate::host_audit::{now_epoch_seconds, summarize_args, write_audit_log, HostAuditEntry};
use crate::host_broker_types::{
    HostBrokerComputerRunRequest, HostBrokerComputerRunResponse, HostBrokerConnectionInfo,
    HostBrokerError, HostBrokerStatus,
};
use crate::process_utils;

const DEFAULT_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 8770;
const HEALTH_PATH: &str = "/api/host/health";
const PERMISSIONS_PATH: &str = "/api/host/permissions";
const COMPUTER_RUN_PATH: &str = "/api/host/computer/run";
const PERMISSION_SUBJECT: &str = "Rumi Viewer";
const MAX_CONCURRENT_REQUESTS: usize = 16;
const MAX_HEADER_BYTES: usize = 1024 * 1024;
const MAX_BODY_BYTES: usize = 1024 * 1024;
const REQUEST_READ_TIMEOUT: Duration = Duration::from_secs(5);
const REQUEST_WRITE_TIMEOUT: Duration = Duration::from_secs(5);
const HELPER_TIMEOUT: Duration = Duration::from_secs(45);
const APPROVAL_TOKEN_VERSION: &str = "v1";

const ARG_HASH_IGNORE_KEYS: &[&str] = &[
    "approval_token",
    "approved",
    "_headers",
    "_method",
    "_raw_body",
    "_raw_body_base64",
];

#[derive(Clone)]
pub struct HostBrokerRuntime {
    inner: Arc<HostBrokerShared>,
}

struct HostBrokerShared {
    config: AppConfig,
    token: Option<String>,
    status: Mutex<HostBrokerStatus>,
    active_requests: Mutex<usize>,
    used_approval_tokens: Mutex<HashSet<String>>,
}

struct ParsedRequest {
    method: String,
    path: String,
    headers: HashMap<String, String>,
    body: Vec<u8>,
}

struct RequestSlot {
    shared: Arc<HostBrokerShared>,
}

impl RequestSlot {
    fn try_acquire(shared: &Arc<HostBrokerShared>) -> Option<Self> {
        let mut active = shared.active_requests.lock().ok()?;
        if *active >= MAX_CONCURRENT_REQUESTS {
            return None;
        }
        *active += 1;
        Some(Self {
            shared: Arc::clone(shared),
        })
    }
}

impl Drop for RequestSlot {
    fn drop(&mut self) {
        if let Ok(mut active) = self.shared.active_requests.lock() {
            *active = active.saturating_sub(1);
        }
    }
}

impl HostBrokerRuntime {
    pub fn start(config: &AppConfig) -> Result<Self> {
        #[cfg(not(target_os = "macos"))]
        {
            return Ok(Self {
                inner: Arc::new(HostBrokerShared {
                    config: config.clone(),
                    token: None,
                    status: Mutex::new(HostBrokerStatus::disabled(
                        "Viewer host broker is only enabled on macOS.",
                    )),
                    active_requests: Mutex::new(0),
                    used_approval_tokens: Mutex::new(HashSet::new()),
                }),
            });
        }

        #[cfg(target_os = "macos")]
        {
            fs::create_dir_all(config.host_broker_dir()).with_context(|| {
                format!(
                    "failed to create host broker directory at {}",
                    config.host_broker_dir().display()
                )
            })?;

            let listener = bind_listener()?;
            let local_addr = listener
                .local_addr()
                .context("failed to read host broker local address")?;
            let port = local_addr.port();
            let url = format!("http://{DEFAULT_HOST}:{port}");
            let token = generate_broker_token();
            let connection = HostBrokerConnectionInfo {
                version: 1,
                host: DEFAULT_HOST.to_string(),
                port,
                url: url.clone(),
                token: token.clone(),
                permission_subject: PERMISSION_SUBJECT.to_string(),
                pid: std::process::id(),
                created_at: now_epoch_seconds(),
            };
            write_connection_file(&config.host_broker_connection_path(), &connection)?;

            let runtime = Self {
                inner: Arc::new(HostBrokerShared {
                    config: config.clone(),
                    token: Some(token),
                    status: Mutex::new(HostBrokerStatus {
                        enabled: true,
                        available: true,
                        status: "running".to_string(),
                        url: Some(url),
                        connection_path: Some(
                            config
                                .host_broker_connection_path()
                                .to_string_lossy()
                                .to_string(),
                        ),
                        recovery: None,
                    }),
                    active_requests: Mutex::new(0),
                    used_approval_tokens: Mutex::new(HashSet::new()),
                }),
            };

            let shared = Arc::clone(&runtime.inner);
            thread::spawn(move || {
                for stream in listener.incoming() {
                    match stream {
                        Ok(mut stream) => {
                            if let Some(slot) = RequestSlot::try_acquire(&shared) {
                                let per_request = Arc::clone(&shared);
                                thread::spawn(move || {
                                    let _slot = slot;
                                    if let Err(error) = handle_stream(stream, &per_request) {
                                        warn!("Viewer host broker request failed: {error}");
                                    }
                                });
                            } else if let Err(error) = write_json_response(
                                &mut stream,
                                503,
                                &json!({"ok": false, "error": {"code": "VIEWER_HOST_BUSY", "message": "Viewer host broker is handling too many requests."}}),
                            ) {
                                warn!("Viewer host broker busy response failed: {error}");
                            }
                        }
                        Err(error) => {
                            error!("Viewer host broker accept failed: {error}");
                            break;
                        }
                    }
                }
            });

            Ok(runtime)
        }
    }

    pub fn status_snapshot(&self) -> HostBrokerStatus {
        self.inner
            .status
            .lock()
            .map(|status| status.clone())
            .unwrap_or_else(|_| HostBrokerStatus {
                enabled: false,
                available: false,
                status: "error".to_string(),
                url: None,
                connection_path: None,
                recovery: Some("Viewer host broker status is unavailable.".to_string()),
            })
    }
}

fn bind_listener() -> Result<TcpListener> {
    TcpListener::bind((DEFAULT_HOST, DEFAULT_PORT))
        .or_else(|_| TcpListener::bind((DEFAULT_HOST, 0)))
        .context("failed to bind Viewer host broker listener")
}

fn generate_broker_token() -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(48)
        .map(char::from)
        .collect()
}

fn write_connection_file(path: &Path, connection: &HostBrokerConnectionInfo) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).with_context(|| {
            format!(
                "failed to create host broker connection parent directory at {}",
                parent.display()
            )
        })?;
    }
    let body = serde_json::to_vec_pretty(connection)
        .context("failed to serialize host broker connection")?;
    fs::write(path, body).with_context(|| {
        format!(
            "failed to write host broker connection file at {}",
            path.display()
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let permissions = fs::Permissions::from_mode(0o600);
        fs::set_permissions(path, permissions).with_context(|| {
            format!(
                "failed to set host broker connection file permissions at {}",
                path.display()
            )
        })?;
    }
    Ok(())
}

fn handle_stream(mut stream: TcpStream, shared: &Arc<HostBrokerShared>) -> Result<()> {
    stream
        .set_read_timeout(Some(REQUEST_READ_TIMEOUT))
        .context("failed to set broker read timeout")?;
    stream
        .set_write_timeout(Some(REQUEST_WRITE_TIMEOUT))
        .context("failed to set broker write timeout")?;
    let request = match read_request(&mut stream) {
        Ok(request) => request,
        Err(error) => {
            let (status_code, body) = read_error_response(&error);
            write_json_response(&mut stream, status_code, &body)?;
            return Ok(());
        }
    };
    let (status_code, body) = route_request(&request, shared);
    write_json_response(&mut stream, status_code, &body)
}

fn read_error_response(error: &anyhow::Error) -> (u16, Value) {
    let message = error.to_string();
    let lowered = message.to_ascii_lowercase();
    if lowered.contains("too large") {
        return (
            413,
            json!({"ok": false, "error": {"code": "REQUEST_TOO_LARGE", "message": message}}),
        );
    }
    (
        400,
        json!({"ok": false, "error": {"code": "BAD_REQUEST", "message": message}}),
    )
}

fn route_request(request: &ParsedRequest, shared: &Arc<HostBrokerShared>) -> (u16, Value) {
    match (request.method.as_str(), request.path.as_str()) {
        ("GET", HEALTH_PATH) => (200, json!({"ok": true, "status": "running"})),
        ("GET", PERMISSIONS_PATH) => {
            if let Err(error) = authorize_request(request, shared) {
                return (
                    401,
                    json!({"ok": false, "error": {"code": "UNAUTHORIZED", "message": error.to_string()}}),
                );
            }
            (
                200,
                json!({
                    "ok": true,
                    "permission_subject": PERMISSION_SUBJECT,
                    "permissions": desktop_system_info::collect_permissions(),
                    "host_broker": shared.status.lock().map(|status| status.clone()).unwrap_or_else(|_| HostBrokerStatus::disabled("Viewer host broker status is unavailable.")),
                }),
            )
        }
        ("POST", COMPUTER_RUN_PATH) => {
            if let Err(error) = authorize_request(request, shared) {
                return (
                    401,
                    json!({"ok": false, "error": {"code": "UNAUTHORIZED", "message": error.to_string()}}),
                );
            }
            match serde_json::from_slice::<HostBrokerComputerRunRequest>(&request.body) {
                Ok(run_request) => (200, execute_computer_run(shared, run_request)),
                Err(error) => (
                    400,
                    json!({"ok": false, "error": {"code": "INVALID_JSON", "message": format!("Invalid JSON payload: {error}")}}),
                ),
            }
        }
        _ => (
            404,
            json!({"ok": false, "error": {"code": "NOT_FOUND", "message": "Not found"}}),
        ),
    }
}

fn authorize_request(request: &ParsedRequest, shared: &HostBrokerShared) -> Result<()> {
    let Some(expected) = shared.token.as_deref() else {
        bail!("Viewer host broker is not enabled");
    };
    let provided =
        parse_auth_token(&request.headers).ok_or_else(|| anyhow!("Missing broker token"))?;
    if provided != expected {
        bail!("Invalid broker token");
    }
    Ok(())
}

fn parse_auth_token(headers: &HashMap<String, String>) -> Option<String> {
    if let Some(value) = headers.get("authorization") {
        let trimmed = value.trim();
        if let Some(token) = trimmed.strip_prefix("Bearer ") {
            let normalized = token.trim();
            if !normalized.is_empty() {
                return Some(normalized.to_string());
            }
        }
    }
    headers
        .get("x-rumi-viewer-broker-token")
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn execute_computer_run(shared: &HostBrokerShared, request: HostBrokerComputerRunRequest) -> Value {
    let raw_function_id = request.function_id.trim().to_string();
    let (function_id, helper_args) = normalize_computer_request(&raw_function_id, &request.args);
    let audit_id = format!("host-audit-{}", generate_broker_token());
    let approval_token = request
        .approval_token
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);
    let approval_token_present = approval_token.is_some();
    let allowed = function_allowed(&function_id);
    if !allowed {
        return serialize_run_response(
            &shared.config,
            HostAuditEntry {
                audit_id: audit_id.clone(),
                ts: now_epoch_seconds(),
                function_id: raw_function_id.clone(),
                profile_id: request.profile_id.clone(),
                pack_id: request.pack_id.clone(),
                conversation_id: request.conversation_id.clone(),
                allowed: false,
                result_ok: false,
                approval_token_present: Some(approval_token_present),
                approval_result: None,
                args_summary: summarize_args(&helper_args),
            },
            HostBrokerComputerRunResponse {
                ok: false,
                function_id: raw_function_id,
                result: None,
                error: Some(HostBrokerError {
                    code: "FUNCTION_NOT_ALLOWED".to_string(),
                    message:
                        "The requested computer function is not allowed by the Viewer host broker."
                            .to_string(),
                }),
                audit_id,
            },
        );
    }

    if high_risk_function(&function_id) && !approval_token_present {
        return serialize_run_response(
            &shared.config,
            HostAuditEntry {
                audit_id: audit_id.clone(),
                ts: now_epoch_seconds(),
                function_id: function_id.clone(),
                profile_id: request.profile_id.clone(),
                pack_id: request.pack_id.clone(),
                conversation_id: request.conversation_id.clone(),
                allowed: false,
                result_ok: false,
                approval_token_present: Some(false),
                approval_result: Some("missing_token".to_string()),
                args_summary: summarize_args(&helper_args),
            },
            HostBrokerComputerRunResponse {
                ok: false,
                function_id: function_id.clone(),
                result: Some(approval_required_payload(&function_id, &helper_args)),
                error: Some(HostBrokerError {
                    code: "APPROVAL_REQUIRED".to_string(),
                    message: "This Viewer-controlled computer action requires an approval token."
                        .to_string(),
                }),
                audit_id,
            },
        );
    }

    let mut viewer_host_approved = false;
    if high_risk_function(&function_id) || approval_token_present {
        let validation = validate_approval_token(
            shared,
            approval_token.as_deref().unwrap_or_default(),
            &raw_function_id,
            &function_id,
            &request.args,
            &helper_args,
            request.pack_id.as_deref().unwrap_or_default(),
            request.conversation_id.as_deref().unwrap_or_default(),
        );
        if let Err(error) = validation {
            return serialize_run_response(
                &shared.config,
                HostAuditEntry {
                    audit_id: audit_id.clone(),
                    ts: now_epoch_seconds(),
                    function_id: function_id.clone(),
                    profile_id: request.profile_id.clone(),
                    pack_id: request.pack_id.clone(),
                    conversation_id: request.conversation_id.clone(),
                    allowed: false,
                    result_ok: false,
                    approval_token_present: Some(approval_token_present),
                    approval_result: Some(error.audit_result.clone()),
                    args_summary: summarize_args(&helper_args),
                },
                HostBrokerComputerRunResponse {
                    ok: false,
                    function_id,
                    result: None,
                    error: Some(HostBrokerError {
                        code: error.code,
                        message: error.message,
                    }),
                    audit_id,
                },
            );
        }
        viewer_host_approved = true;
    }

    let helper_result = run_computer_helper(
        &shared.config,
        &function_id,
        &helper_args,
        request.artifact_root.as_deref(),
        viewer_host_approved,
    );
    match helper_result {
        Ok(result) => {
            let result_ok = result.get("ok").and_then(Value::as_bool).unwrap_or(false);
            let mut payload = result.get("result").cloned();
            let payload_requires_approval = helper_payload_requires_approval(payload.as_ref());
            if payload_requires_approval {
                payload = payload.map(redact_helper_approval_token);
            }
            let approval_result = approval_result_for(
                &function_id,
                approval_token_present,
                payload_requires_approval,
            );
            let helper_error_code = result
                .get("error_code")
                .and_then(Value::as_str)
                .unwrap_or(if payload_requires_approval {
                    "APPROVAL_REQUIRED"
                } else {
                    "VIEWER_HOST_FAILED"
                })
                .to_string();
            let error_message = result
                .get("error")
                .and_then(Value::as_str)
                .unwrap_or(if payload_requires_approval {
                    "This Viewer-controlled computer action requires approval."
                } else {
                    "Viewer host helper failed"
                })
                .to_string();
            serialize_run_response(
                &shared.config,
                HostAuditEntry {
                    audit_id: audit_id.clone(),
                    ts: now_epoch_seconds(),
                    function_id: function_id.clone(),
                    profile_id: request.profile_id.clone(),
                    pack_id: request.pack_id.clone(),
                    conversation_id: request.conversation_id.clone(),
                    allowed: true,
                    result_ok: result_ok && !payload_requires_approval,
                    approval_token_present: Some(approval_token_present),
                    approval_result,
                    args_summary: summarize_args(&helper_args),
                },
                if result_ok && !payload_requires_approval {
                    HostBrokerComputerRunResponse {
                        ok: true,
                        function_id,
                        result: payload,
                        error: None,
                        audit_id,
                    }
                } else {
                    HostBrokerComputerRunResponse {
                        ok: false,
                        function_id,
                        result: payload,
                        error: Some(HostBrokerError {
                            code: helper_error_code,
                            message: error_message,
                        }),
                        audit_id,
                    }
                },
            )
        }
        Err(error) => {
            let code = helper_error_code(&error).to_string();
            serialize_run_response(
                &shared.config,
                HostAuditEntry {
                    audit_id: audit_id.clone(),
                    ts: now_epoch_seconds(),
                    function_id: function_id.clone(),
                    profile_id: request.profile_id.clone(),
                    pack_id: request.pack_id.clone(),
                    conversation_id: request.conversation_id.clone(),
                    allowed: true,
                    result_ok: false,
                    approval_token_present: Some(approval_token_present),
                    approval_result: if high_risk_function(&function_id) && approval_token_present {
                        Some("helper_error".to_string())
                    } else {
                        approval_result_for(&function_id, approval_token_present, false)
                    },
                    args_summary: summarize_args(&helper_args),
                },
                HostBrokerComputerRunResponse {
                    ok: false,
                    function_id,
                    result: None,
                    error: Some(HostBrokerError {
                        code,
                        message: error.to_string(),
                    }),
                    audit_id,
                },
            )
        }
    }
}

fn serialize_run_response(
    config: &AppConfig,
    audit: HostAuditEntry,
    response: HostBrokerComputerRunResponse,
) -> Value {
    if let Err(error) = write_audit_log(&config.host_broker_audit_log_path(), &audit) {
        warn!("Failed to write Viewer host broker audit log: {error}");
    }
    serde_json::to_value(response).unwrap_or_else(|_| {
        json!({"ok": false, "error": {"code": "SERIALIZATION_FAILED", "message": "Could not serialize broker response"}})
    })
}

fn approval_required_payload(function_id: &str, args: &Value) -> Value {
    json!({
        "action": function_id,
        "requires_approval": true,
        "approval_required": true,
        "approval_hint": "Repeat the same action after explicit user confirmation.",
        "payload": strip_approval_fields(args),
    })
}

fn normalize_computer_request(function_id: &str, args: &Value) -> (String, Value) {
    let normalized = normalize_function_id(function_id);
    if normalized == "computer.key"
        && matches!(
            function_id.trim(),
            "computer.backspace" | "computer.delete_back"
        )
    {
        let mut map = match args {
            Value::Object(existing) => existing.clone(),
            _ => Map::new(),
        };
        if !map.contains_key("key") && !map.contains_key("key_combo") {
            map.insert("key".to_string(), Value::String("backspace".to_string()));
        }
        return (normalized, Value::Object(map));
    }
    (normalized, args.clone())
}

fn normalize_function_id(function_id: &str) -> String {
    match function_id.trim() {
        "computer.backspace" | "computer.delete_back" => "computer.key".to_string(),
        other => other.to_string(),
    }
}

fn strip_approval_fields(args: &Value) -> Value {
    let Value::Object(map) = args else {
        return args.clone();
    };
    let mut stripped = Map::new();
    for (key, value) in map {
        if ARG_HASH_IGNORE_KEYS.contains(&key.as_str()) {
            continue;
        }
        stripped.insert(key.clone(), value.clone());
    }
    Value::Object(stripped)
}

fn function_allowed(function_id: &str) -> bool {
    matches!(
        function_id,
        "computer.doctor"
            | "computer.observe"
            | "computer.screenshot"
            | "computer.context"
            | "computer.apps"
            | "computer.windows"
            | "computer.select_app"
            | "computer.show_app"
            | "computer.select_window"
            | "computer.move"
            | "computer.click"
            | "computer.drag"
            | "computer.type"
            | "computer.key"
            | "computer.scroll"
            | "computer.semantic_action"
            | "computer.pid_event"
            | "computer.clipboard.read"
            | "computer.clipboard.write"
            | "computer.clipboard.clear"
    )
}

fn helper_payload_requires_approval(payload: Option<&Value>) -> bool {
    let Some(Value::Object(map)) = payload else {
        return false;
    };
    map.get("requires_approval")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        || map
            .get("approval_required")
            .and_then(Value::as_bool)
            .unwrap_or(false)
}

fn redact_helper_approval_token(payload: Value) -> Value {
    let Value::Object(mut map) = payload else {
        return payload;
    };
    map.remove("approval_token");
    if let Some(nested_payload) = map.get_mut("payload") {
        *nested_payload = strip_approval_fields(nested_payload);
    }
    Value::Object(map)
}

fn approval_result_for(
    function_id: &str,
    approval_token_present: bool,
    payload_requires_approval: bool,
) -> Option<String> {
    if high_risk_function(function_id) {
        return Some(
            if !approval_token_present {
                "missing_token"
            } else if payload_requires_approval {
                "rejected"
            } else {
                "approved"
            }
            .to_string(),
        );
    }
    if payload_requires_approval {
        return Some("requires_approval".to_string());
    }
    None
}

fn high_risk_function(function_id: &str) -> bool {
    matches!(
        function_id,
        "computer.screenshot"
            | "computer.move"
            | "computer.click"
            | "computer.drag"
            | "computer.type"
            | "computer.key"
            | "computer.scroll"
            | "computer.semantic_action"
            | "computer.pid_event"
            | "computer.clipboard.read"
            | "computer.clipboard.write"
            | "computer.clipboard.clear"
    )
}

#[derive(Debug, Clone)]
struct ApprovalValidationError {
    code: String,
    message: String,
    audit_result: String,
}

#[derive(Debug, Clone, Deserialize)]
struct ApprovalTokenPayload {
    version: String,
    jti: String,
    args_hash: String,
    expires_at: u64,
    #[serde(default)]
    operation: String,
    #[serde(default)]
    function_id: String,
    #[serde(default)]
    pack_id: String,
    #[serde(default)]
    conversation_id: String,
}

fn validate_approval_token(
    shared: &HostBrokerShared,
    token: &str,
    raw_function_id: &str,
    function_id: &str,
    raw_args: &Value,
    helper_args: &Value,
    pack_id: &str,
    conversation_id: &str,
) -> std::result::Result<(), ApprovalValidationError> {
    let payload = decode_approval_token(&shared.config, token)?;
    if payload.version != APPROVAL_TOKEN_VERSION {
        return Err(approval_error(
            "APPROVAL_TOKEN_INVALID",
            "approval token version is invalid",
            "invalid_token",
        ));
    }
    if payload.expires_at < now_epoch_seconds() {
        return Err(approval_error(
            "APPROVAL_EXPIRED",
            "approval token expired",
            "expired_token",
        ));
    }

    let token_function = normalize_function_id(if payload.function_id.trim().is_empty() {
        &payload.operation
    } else {
        &payload.function_id
    });
    let raw_request_function = normalize_function_id(raw_function_id);
    if token_function != function_id && token_function != raw_request_function {
        return Err(approval_error(
            "APPROVAL_OPERATION_MISMATCH",
            "approval token operation mismatch",
            "operation_mismatch",
        ));
    }

    let mut acceptable_hashes = HashSet::new();
    acceptable_hashes.insert(hash_arguments_value(raw_args));
    acceptable_hashes.insert(hash_arguments_value(helper_args));
    if !acceptable_hashes.contains(&payload.args_hash) {
        return Err(approval_error(
            "APPROVAL_ARGUMENTS_CHANGED",
            "approval token does not match request arguments",
            "arguments_changed",
        ));
    }

    if payload.pack_id != pack_id {
        return Err(approval_error(
            "APPROVAL_PACK_MISMATCH",
            "approval token pack mismatch",
            "pack_mismatch",
        ));
    }
    if payload.conversation_id != conversation_id {
        return Err(approval_error(
            "APPROVAL_CONVERSATION_MISMATCH",
            "approval token conversation mismatch",
            "conversation_mismatch",
        ));
    }

    let mut used = shared.used_approval_tokens.lock().map_err(|_| {
        approval_error(
            "APPROVAL_TOKEN_INVALID",
            "approval token state is unavailable",
            "token_state_error",
        )
    })?;
    if used.contains(&payload.jti) {
        return Err(approval_error(
            "APPROVAL_TOKEN_USED",
            "approval token has already been used",
            "token_used",
        ));
    }
    used.insert(payload.jti);
    Ok(())
}

fn approval_error(code: &str, message: &str, audit_result: &str) -> ApprovalValidationError {
    ApprovalValidationError {
        code: code.to_string(),
        message: message.to_string(),
        audit_result: audit_result.to_string(),
    }
}

fn decode_approval_token(
    config: &AppConfig,
    token: &str,
) -> std::result::Result<ApprovalTokenPayload, ApprovalValidationError> {
    let Some((encoded, signature)) = token.rsplit_once('.') else {
        return Err(approval_error(
            "APPROVAL_TOKEN_MISSING",
            "approval token is required",
            "missing_token",
        ));
    };
    let secret = approval_runtime_secret(config)?;
    let expected = URL_SAFE_NO_PAD.encode(hmac_sha256(secret.as_bytes(), encoded.as_bytes()));
    if !constant_time_eq(signature.as_bytes(), expected.as_bytes()) {
        return Err(approval_error(
            "APPROVAL_SIGNATURE_INVALID",
            "approval token signature is invalid",
            "invalid_signature",
        ));
    }
    let decoded = URL_SAFE_NO_PAD.decode(encoded).map_err(|_| {
        approval_error(
            "APPROVAL_TOKEN_INVALID",
            "approval token payload is invalid",
            "invalid_token",
        )
    })?;
    serde_json::from_slice::<ApprovalTokenPayload>(&decoded).map_err(|_| {
        approval_error(
            "APPROVAL_TOKEN_INVALID",
            "approval token payload is invalid",
            "invalid_token",
        )
    })
}

fn approval_runtime_secret(
    config: &AppConfig,
) -> std::result::Result<String, ApprovalValidationError> {
    if let Ok(value) = std::env::var("RUMI_DEFAULTSPACK_APPROVAL_SECRET") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }
    let path = config
        .app_dir
        .join("ecosystem")
        .join("defaultspack")
        .join("user_data")
        .join("safety")
        .join("approval_runtime_secret");
    fs::read_to_string(&path)
        .map(|value| value.trim().to_string())
        .ok()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            approval_error(
                "APPROVAL_TOKEN_UNVERIFIABLE",
                "approval token signing secret is unavailable",
                "unverifiable_token",
            )
        })
}

fn hash_arguments_value(args: &Value) -> String {
    let canonical = canonicalize_for_hash(args);
    let body = serde_json::to_string(&canonical).unwrap_or_else(|_| "{}".to_string());
    hex_sha256(body.as_bytes())
}

fn canonicalize_for_hash(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut canonical = Map::new();
            for (key, item) in map {
                if ARG_HASH_IGNORE_KEYS.contains(&key.as_str()) {
                    continue;
                }
                canonical.insert(key.clone(), canonicalize_for_hash(item));
            }
            Value::Object(canonical)
        }
        Value::Array(items) => Value::Array(items.iter().map(canonicalize_for_hash).collect()),
        other => other.clone(),
    }
}

fn hmac_sha256(key: &[u8], message: &[u8]) -> [u8; 32] {
    const BLOCK_SIZE: usize = 64;
    let mut normalized_key = [0_u8; BLOCK_SIZE];
    if key.len() > BLOCK_SIZE {
        let digest = Sha256::digest(key);
        normalized_key[..digest.len()].copy_from_slice(&digest);
    } else {
        normalized_key[..key.len()].copy_from_slice(key);
    }
    let mut ipad = [0x36_u8; BLOCK_SIZE];
    let mut opad = [0x5c_u8; BLOCK_SIZE];
    for index in 0..BLOCK_SIZE {
        ipad[index] ^= normalized_key[index];
        opad[index] ^= normalized_key[index];
    }

    let mut inner = Sha256::new();
    inner.update(ipad);
    inner.update(message);
    let inner_digest = inner.finalize();

    let mut outer = Sha256::new();
    outer.update(opad);
    outer.update(inner_digest);
    outer.finalize().into()
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut diff = 0_u8;
    for (left_byte, right_byte) in left.iter().zip(right.iter()) {
        diff |= left_byte ^ right_byte;
    }
    diff == 0
}

fn hex_sha256(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut output = String::with_capacity(digest.len() * 2);
    for byte in digest {
        output.push_str(&format!("{byte:02x}"));
    }
    output
}

#[derive(Debug)]
enum ComputerHelperError {
    Timeout,
    Failed(anyhow::Error),
}

impl std::fmt::Display for ComputerHelperError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Timeout => write!(formatter, "Viewer host helper timed out"),
            Self::Failed(error) => write!(formatter, "{error}"),
        }
    }
}

fn helper_error_code(error: &ComputerHelperError) -> &'static str {
    match error {
        ComputerHelperError::Timeout => "VIEWER_HOST_TIMEOUT",
        ComputerHelperError::Failed(_) => "VIEWER_HOST_FAILED",
    }
}

fn run_computer_helper(
    config: &AppConfig,
    function_id: &str,
    args: &Value,
    artifact_root: Option<&str>,
    viewer_host_approved: bool,
) -> std::result::Result<Value, ComputerHelperError> {
    let helper_path = config
        .app_dir
        .join("core_runtime")
        .join("host_broker")
        .join("computer_host_helper.py");
    if !helper_path.exists() {
        return Err(ComputerHelperError::Failed(anyhow!(
            "Viewer host helper is missing at {}",
            helper_path.display()
        )));
    }

    let mut child = process_utils::command(config.venv_python())
        .arg(helper_path)
        .current_dir(&config.app_dir)
        .env("RUMI_HOME", &config.rumi_home)
        .env("RUMI_USER_DATA", &config.user_data_dir)
        .env("RUMI_LOG_DIR", &config.log_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| {
            ComputerHelperError::Failed(
                anyhow!(error).context("failed to start Viewer host helper"),
            )
        })?;

    let body = json!({
        "function_id": function_id,
        "args": args,
        "artifact_root": artifact_root,
        "viewer_host_approved": viewer_host_approved,
    });

    if let Some(stdin) = child.stdin.as_mut() {
        stdin
            .write_all(
                serde_json::to_string(&body)
                    .map_err(|error| {
                        ComputerHelperError::Failed(
                            anyhow!(error).context("failed to encode Viewer host helper request"),
                        )
                    })?
                    .as_bytes(),
            )
            .map_err(|error| {
                ComputerHelperError::Failed(
                    anyhow!(error).context("failed to write Viewer host helper request"),
                )
            })?;
    }
    drop(child.stdin.take());

    let stdout_handle = child.stdout.take().map(|mut stdout| {
        thread::spawn(move || {
            let mut bytes = Vec::new();
            let _ = stdout.read_to_end(&mut bytes);
            bytes
        })
    });
    let stderr_handle = child.stderr.take().map(|mut stderr| {
        thread::spawn(move || {
            let mut bytes = Vec::new();
            let _ = stderr.read_to_end(&mut bytes);
            bytes
        })
    });

    let status = wait_for_helper_status(&mut child, HELPER_TIMEOUT)?;
    let stdout = join_output(stdout_handle);
    let stderr = join_output(stderr_handle);
    if !status.success() {
        let stderr = String::from_utf8_lossy(&stderr).trim().to_string();
        return Err(ComputerHelperError::Failed(anyhow!(
            "Viewer host helper exited with status {}: {}",
            status,
            stderr
        )));
    }
    let stdout = String::from_utf8(stdout).map_err(|error| {
        ComputerHelperError::Failed(
            anyhow!(error).context("Viewer host helper returned non-utf8 output"),
        )
    })?;
    serde_json::from_str(stdout.trim()).map_err(|error| {
        ComputerHelperError::Failed(
            anyhow!(error).context("failed to decode Viewer host helper response"),
        )
    })
}

fn wait_for_helper_status(
    child: &mut std::process::Child,
    timeout: Duration,
) -> std::result::Result<ExitStatus, ComputerHelperError> {
    let started = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|error| {
            ComputerHelperError::Failed(
                anyhow!(error).context("failed to wait for Viewer host helper"),
            )
        })? {
            return Ok(status);
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            return Err(ComputerHelperError::Timeout);
        }
        thread::sleep(Duration::from_millis(25));
    }
}

fn join_output(handle: Option<thread::JoinHandle<Vec<u8>>>) -> Vec<u8> {
    handle
        .and_then(|handle| handle.join().ok())
        .unwrap_or_default()
}

fn read_request(stream: &mut TcpStream) -> Result<ParsedRequest> {
    let mut buffer = Vec::new();
    let mut chunk = [0_u8; 4096];
    let mut header_end = None;

    while header_end.is_none() {
        let read = stream
            .read(&mut chunk)
            .context("failed to read broker request")?;
        if read == 0 {
            break;
        }
        buffer.extend_from_slice(&chunk[..read]);
        header_end = find_header_end(&buffer);
        if buffer.len() > MAX_HEADER_BYTES {
            bail!("broker request headers too large");
        }
    }

    let header_end = header_end.ok_or_else(|| anyhow!("malformed broker request"))?;
    let header_bytes = &buffer[..header_end];
    let header_text = String::from_utf8_lossy(header_bytes);
    let mut lines = header_text.split("\r\n");
    let request_line = lines
        .next()
        .ok_or_else(|| anyhow!("missing broker request line"))?;
    let mut parts = request_line.split_whitespace();
    let method = parts.next().unwrap_or_default().to_string();
    let path = parts.next().unwrap_or_default().to_string();
    let mut headers = HashMap::new();
    for line in lines {
        if let Some((name, value)) = line.split_once(':') {
            headers.insert(name.trim().to_ascii_lowercase(), value.trim().to_string());
        }
    }
    let content_length = content_length_from_headers(&headers)?;
    if content_length > MAX_BODY_BYTES {
        bail!("broker request body too large");
    }
    let mut body = buffer[header_end + 4..].to_vec();
    if body.len() > MAX_BODY_BYTES {
        bail!("broker request body too large");
    }
    while body.len() < content_length {
        let read = stream
            .read(&mut chunk)
            .context("failed to read broker request body")?;
        if read == 0 {
            break;
        }
        body.extend_from_slice(&chunk[..read]);
        if body.len() > MAX_BODY_BYTES {
            bail!("broker request body too large");
        }
    }
    if body.len() < content_length {
        bail!("broker request body incomplete");
    }
    body.truncate(content_length);

    Ok(ParsedRequest {
        method,
        path,
        headers,
        body,
    })
}

fn content_length_from_headers(headers: &HashMap<String, String>) -> Result<usize> {
    let Some(value) = headers.get("content-length") else {
        return Ok(0);
    };
    let parsed = value
        .parse::<usize>()
        .with_context(|| format!("invalid broker request content-length: {value}"))?;
    Ok(parsed)
}

fn find_header_end(buffer: &[u8]) -> Option<usize> {
    buffer.windows(4).position(|window| window == b"\r\n\r\n")
}

fn write_json_response(stream: &mut TcpStream, status_code: u16, body: &Value) -> Result<()> {
    let status_text = match status_code {
        200 => "OK",
        400 => "Bad Request",
        401 => "Unauthorized",
        404 => "Not Found",
        413 => "Payload Too Large",
        503 => "Service Unavailable",
        _ => "Internal Server Error",
    };
    let body_text =
        serde_json::to_string(body).context("failed to serialize broker response body")?;
    let response = format!(
        "HTTP/1.1 {status_code} {status_text}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body_text.len(),
        body_text
    );
    stream
        .write_all(response.as_bytes())
        .context("failed to write broker response")?;
    stream.flush().context("failed to flush broker response")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_authorization_header_accepts_bearer_and_custom_token() {
        let mut headers = HashMap::new();
        headers.insert("authorization".to_string(), "Bearer abc123".to_string());
        assert_eq!(parse_auth_token(&headers).as_deref(), Some("abc123"));

        headers.clear();
        headers.insert(
            "x-rumi-viewer-broker-token".to_string(),
            "direct-token".to_string(),
        );
        assert_eq!(parse_auth_token(&headers).as_deref(), Some("direct-token"));
    }

    #[test]
    fn write_connection_file_persists_json_payload() {
        let temp_dir =
            std::env::temp_dir().join(format!("rumi-host-broker-test-{}", generate_broker_token()));
        let path = temp_dir.join("connection.json");
        let info = HostBrokerConnectionInfo {
            version: 1,
            host: DEFAULT_HOST.to_string(),
            port: DEFAULT_PORT,
            url: format!("http://{DEFAULT_HOST}:{DEFAULT_PORT}"),
            token: "secret".to_string(),
            permission_subject: PERMISSION_SUBJECT.to_string(),
            pid: 42,
            created_at: 123,
        };
        write_connection_file(&path, &info).expect("connection file should be written");
        let stored: HostBrokerConnectionInfo =
            serde_json::from_slice(&fs::read(&path).expect("connection file should be readable"))
                .expect("connection file JSON should parse");
        assert_eq!(stored.permission_subject, PERMISSION_SUBJECT);
        assert_eq!(stored.port, DEFAULT_PORT);
        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn high_risk_functions_require_approval() {
        assert!(high_risk_function("computer.click"));
        assert!(high_risk_function("computer.move"));
        assert!(high_risk_function("computer.screenshot"));
        assert!(high_risk_function("computer.clipboard.read"));
        assert!(function_allowed("computer.clipboard.clear"));
        assert!(!function_allowed("computer.launch_missiles"));
    }

    #[test]
    fn helper_payload_approval_detection_matches_browser_controller_schema() {
        assert!(helper_payload_requires_approval(Some(
            &json!({"requires_approval": true})
        )));
        assert!(helper_payload_requires_approval(Some(
            &json!({"approval_required": true})
        )));
        assert!(!helper_payload_requires_approval(Some(
            &json!({"requires_approval": false})
        )));
    }

    #[test]
    fn helper_approval_payload_redaction_removes_harvestable_tokens() {
        let redacted = redact_helper_approval_token(json!({
            "action": "computer.clipboard.read",
            "requires_approval": true,
            "approval_token": "helper-issued-token",
            "payload": {
                "include_content": true,
                "approval_token": "nested-token",
                "text": "keep"
            }
        }));

        assert!(redacted.get("approval_token").is_none());
        assert_eq!(
            redacted.pointer("/payload/text").and_then(Value::as_str),
            Some("keep")
        );
        assert!(redacted.pointer("/payload/approval_token").is_none());
    }

    #[test]
    fn approval_result_tracks_missing_rejected_and_approved_states() {
        assert_eq!(
            approval_result_for("computer.click", false, false).as_deref(),
            Some("missing_token")
        );
        assert_eq!(
            approval_result_for("computer.click", true, true).as_deref(),
            Some("rejected")
        );
        assert_eq!(
            approval_result_for("computer.click", true, false).as_deref(),
            Some("approved")
        );
        assert_eq!(
            approval_result_for("computer.screenshot", true, true).as_deref(),
            Some("rejected")
        );
    }

    #[test]
    fn broker_rejects_fake_approval_token_for_high_risk_action() {
        let (config, temp_dir) = test_config_with_approval_secret("secret");
        let shared = test_shared(config);
        let result = validate_approval_token(
            &shared,
            "fake-token",
            "computer.click",
            "computer.click",
            &json!({"x": 10, "y": 10}),
            &json!({"x": 10, "y": 10}),
            "defaultspack",
            "conv-1",
        );

        let error = result.expect_err("fake token should be rejected");
        assert_eq!(error.code, "APPROVAL_TOKEN_MISSING");
        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn broker_rejects_approval_token_for_different_action() {
        let (config, temp_dir) = test_config_with_approval_secret("secret");
        let shared = test_shared(config);
        let args = json!({"text": "hello"});
        let token = signed_test_approval_token(
            "secret",
            json!({
                "version": APPROVAL_TOKEN_VERSION,
                "jti": "tok-action",
                "operation": "computer.screenshot",
                "function_id": "computer.screenshot",
                "args_hash": hash_arguments_value(&args),
                "pack_id": "defaultspack",
                "conversation_id": "conv-1",
                "expires_at": now_epoch_seconds() + 60,
            }),
        );

        let result = validate_approval_token(
            &shared,
            &token,
            "computer.type",
            "computer.type",
            &args,
            &args,
            "defaultspack",
            "conv-1",
        );

        let error = result.expect_err("wrong action should be rejected");
        assert_eq!(error.code, "APPROVAL_OPERATION_MISMATCH");
        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn broker_rejects_approval_token_when_arguments_change() {
        let (config, temp_dir) = test_config_with_approval_secret("secret");
        let shared = test_shared(config);
        let approved_args = json!({"x": 10, "y": 10});
        let changed_args = json!({"x": 20, "y": 20});
        let token = signed_test_approval_token(
            "secret",
            json!({
                "version": APPROVAL_TOKEN_VERSION,
                "jti": "tok-args",
                "operation": "computer.click",
                "function_id": "computer.click",
                "args_hash": hash_arguments_value(&approved_args),
                "pack_id": "defaultspack",
                "conversation_id": "conv-1",
                "expires_at": now_epoch_seconds() + 60,
            }),
        );

        let result = validate_approval_token(
            &shared,
            &token,
            "computer.click",
            "computer.click",
            &changed_args,
            &changed_args,
            "defaultspack",
            "conv-1",
        );

        let error = result.expect_err("changed args should be rejected");
        assert_eq!(error.code, "APPROVAL_ARGUMENTS_CHANGED");
        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn broker_rejects_expired_approval_token() {
        let (config, temp_dir) = test_config_with_approval_secret("secret");
        let shared = test_shared(config);
        let args = json!({"x": 10, "y": 10});
        let token = signed_test_approval_token(
            "secret",
            json!({
                "version": APPROVAL_TOKEN_VERSION,
                "jti": "tok-expired",
                "operation": "computer.click",
                "function_id": "computer.click",
                "args_hash": hash_arguments_value(&args),
                "pack_id": "defaultspack",
                "conversation_id": "conv-1",
                "expires_at": now_epoch_seconds().saturating_sub(1),
            }),
        );

        let result = validate_approval_token(
            &shared,
            &token,
            "computer.click",
            "computer.click",
            &args,
            &args,
            "defaultspack",
            "conv-1",
        );

        let error = result.expect_err("expired token should be rejected");
        assert_eq!(error.code, "APPROVAL_EXPIRED");
        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn broker_normalizes_backspace_alias_before_whitelist() {
        let (function_id, args) =
            normalize_computer_request("computer.backspace", &json!({"count": 2}));

        assert_eq!(function_id, "computer.key");
        assert!(function_allowed(&function_id));
        assert_eq!(args.get("key").and_then(Value::as_str), Some("backspace"));
        assert_eq!(args.get("count").and_then(Value::as_i64), Some(2));
    }

    #[test]
    fn argument_hash_matches_defaultspack_approval_hash() {
        assert_eq!(
            hash_arguments_value(&json!({"x": 10, "y": 10})),
            "b5e1c3939b7c2f06da65d735b99d881c5bf6143e313b908c028b80aaa4dfabfc"
        );
        assert_eq!(
            hash_arguments_value(&json!({"text": "あ", "approval_token": "tok"})),
            "a93f199e5601efaaa265174dfdd9d291ee80085bd9d2dd2dfb88d59b33b9d247"
        );
    }

    #[test]
    fn oversized_content_length_maps_to_payload_too_large() {
        let mut headers = HashMap::new();
        headers.insert(
            "content-length".to_string(),
            (MAX_BODY_BYTES + 1).to_string(),
        );
        let error = match content_length_from_headers(&headers).and_then(|length| {
            if length > MAX_BODY_BYTES {
                return Err(anyhow!("broker request body too large"));
            }
            Ok(length)
        }) {
            Ok(_) => panic!("oversized body should fail"),
            Err(error) => error,
        };

        let (status, body) = read_error_response(&error);
        assert_eq!(status, 413);
        assert_eq!(
            body.pointer("/error/code").and_then(Value::as_str),
            Some("REQUEST_TOO_LARGE")
        );
    }

    #[test]
    fn helper_timeout_maps_to_timeout_error_code() {
        assert_eq!(
            helper_error_code(&ComputerHelperError::Timeout),
            "VIEWER_HOST_TIMEOUT"
        );
    }

    #[test]
    fn request_slot_enforces_concurrency_limit() {
        let (config, temp_dir) = test_config_with_approval_secret("secret");
        let shared = Arc::new(test_shared(config));
        let mut slots = Vec::new();
        for _ in 0..MAX_CONCURRENT_REQUESTS {
            slots.push(RequestSlot::try_acquire(&shared).expect("slot should be available"));
        }

        assert!(RequestSlot::try_acquire(&shared).is_none());
        drop(slots.pop());
        assert!(RequestSlot::try_acquire(&shared).is_some());
        let _ = fs::remove_dir_all(temp_dir);
    }

    fn signed_test_approval_token(secret: &str, payload: Value) -> String {
        let encoded = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&payload).unwrap());
        let signature = URL_SAFE_NO_PAD.encode(hmac_sha256(secret.as_bytes(), encoded.as_bytes()));
        format!("{encoded}.{signature}")
    }

    fn test_config_with_approval_secret(secret: &str) -> (AppConfig, std::path::PathBuf) {
        let temp_dir =
            std::env::temp_dir().join(format!("rumi-host-broker-test-{}", generate_broker_token()));
        let app_dir = temp_dir.join("app");
        let safety_dir = app_dir
            .join("ecosystem")
            .join("defaultspack")
            .join("user_data")
            .join("safety");
        fs::create_dir_all(&safety_dir).expect("safety dir should be created");
        fs::write(safety_dir.join("approval_runtime_secret"), secret)
            .expect("approval secret should be written");
        let config = AppConfig {
            app_dir: app_dir.clone(),
            rumi_home: app_dir,
            python_dir: temp_dir.join("python"),
            uv_path: temp_dir.join("uv"),
            venv_dir: temp_dir.join("venv"),
            user_data_dir: temp_dir.join("user_data"),
            log_dir: temp_dir.join("logs"),
            kernel_port: 8765,
            dev_workspace_root: None,
        };
        (config, temp_dir)
    }

    fn test_shared(config: AppConfig) -> HostBrokerShared {
        HostBrokerShared {
            config,
            token: Some("broker-token".to_string()),
            status: Mutex::new(HostBrokerStatus::disabled("test")),
            active_requests: Mutex::new(0),
            used_approval_tokens: Mutex::new(HashSet::new()),
        }
    }
}
