use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::thread;

use anyhow::{anyhow, bail, Context, Result};
use log::{error, warn};
use rand::{distributions::Alphanumeric, Rng};
use serde_json::{json, Value};

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

#[derive(Clone)]
pub struct HostBrokerRuntime {
    inner: Arc<HostBrokerShared>,
}

struct HostBrokerShared {
    config: AppConfig,
    token: Option<String>,
    status: Mutex<HostBrokerStatus>,
}

struct ParsedRequest {
    method: String,
    path: String,
    headers: HashMap<String, String>,
    body: Vec<u8>,
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
                }),
            };

            let shared = Arc::clone(&runtime.inner);
            thread::spawn(move || {
                for stream in listener.incoming() {
                    match stream {
                        Ok(stream) => {
                            let per_request = Arc::clone(&shared);
                            thread::spawn(move || {
                                if let Err(error) = handle_stream(stream, &per_request) {
                                    warn!("Viewer host broker request failed: {error}");
                                }
                            });
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
    let request = read_request(&mut stream)?;
    let (status_code, body) = route_request(&request, shared);
    write_json_response(&mut stream, status_code, &body)
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
    let function_id = request.function_id.trim().to_string();
    let audit_id = format!("host-audit-{}", generate_broker_token());
    let approval_token_present = request
        .approval_token
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .is_some();
    let allowed = function_allowed(&function_id);
    if !allowed {
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
                approval_result: None,
                args_summary: summarize_args(&request.args),
            },
            HostBrokerComputerRunResponse {
                ok: false,
                function_id,
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
                args_summary: summarize_args(&request.args),
            },
            HostBrokerComputerRunResponse {
                ok: false,
                function_id,
                result: None,
                error: Some(HostBrokerError {
                    code: "APPROVAL_REQUIRED".to_string(),
                    message: "This Viewer-controlled computer action requires an approval token."
                        .to_string(),
                }),
                audit_id,
            },
        );
    }

    let helper_result = run_computer_helper(
        &shared.config,
        &request.function_id,
        &request.args,
        request.artifact_root.as_deref(),
    );
    match helper_result {
        Ok(result) => {
            let result_ok = result.get("ok").and_then(Value::as_bool).unwrap_or(false);
            let payload = result.get("result").cloned();
            let payload_requires_approval = helper_payload_requires_approval(payload.as_ref());
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
                    args_summary: summarize_args(&request.args),
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
        Err(error) => serialize_run_response(
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
                args_summary: summarize_args(&request.args),
            },
            HostBrokerComputerRunResponse {
                ok: false,
                function_id,
                result: None,
                error: Some(HostBrokerError {
                    code: "VIEWER_HOST_FAILED".to_string(),
                    message: error.to_string(),
                }),
                audit_id,
            },
        ),
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
        "computer.click"
            | "computer.drag"
            | "computer.type"
            | "computer.key"
            | "computer.scroll"
            | "computer.semantic_action"
            | "computer.pid_event"
            | "computer.clipboard.write"
            | "computer.clipboard.clear"
    )
}

fn run_computer_helper(
    config: &AppConfig,
    function_id: &str,
    args: &Value,
    artifact_root: Option<&str>,
) -> Result<Value> {
    let helper_path = config
        .app_dir
        .join("core_runtime")
        .join("host_broker")
        .join("computer_host_helper.py");
    if !helper_path.exists() {
        bail!("Viewer host helper is missing at {}", helper_path.display());
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
        .context("failed to start Viewer host helper")?;

    let body = json!({
        "function_id": function_id,
        "args": args,
        "artifact_root": artifact_root,
    });

    if let Some(stdin) = child.stdin.as_mut() {
        stdin
            .write_all(
                serde_json::to_string(&body)
                    .context("failed to encode Viewer host helper request")?
                    .as_bytes(),
            )
            .context("failed to write Viewer host helper request")?;
    }

    let output = child
        .wait_with_output()
        .context("failed to wait for Viewer host helper")?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        bail!(
            "Viewer host helper exited with status {}: {}",
            output.status,
            stderr
        );
    }
    let stdout =
        String::from_utf8(output.stdout).context("Viewer host helper returned non-utf8 output")?;
    serde_json::from_str(stdout.trim()).context("failed to decode Viewer host helper response")
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
        if buffer.len() > 1024 * 1024 {
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
    let content_length = headers
        .get("content-length")
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(0);
    let mut body = buffer[header_end + 4..].to_vec();
    while body.len() < content_length {
        let read = stream
            .read(&mut chunk)
            .context("failed to read broker request body")?;
        if read == 0 {
            break;
        }
        body.extend_from_slice(&chunk[..read]);
    }
    body.truncate(content_length);

    Ok(ParsedRequest {
        method,
        path,
        headers,
        body,
    })
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
        assert!(!high_risk_function("computer.screenshot"));
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
            Some("requires_approval")
        );
    }
}
