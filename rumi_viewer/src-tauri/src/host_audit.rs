use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use serde::Serialize;
use serde_json::{Map, Value};

#[derive(Debug, Clone, Serialize)]
pub struct HostAuditEntry {
    pub audit_id: String,
    pub ts: u64,
    pub function_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub profile_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pack_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub conversation_id: Option<String>,
    pub allowed: bool,
    pub result_ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub approval_token_present: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub approval_result: Option<String>,
    pub args_summary: Value,
}

pub fn now_epoch_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

pub fn write_audit_log(path: &Path, entry: &HostAuditEntry) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).with_context(|| {
            format!(
                "failed to create host broker audit dir at {}",
                parent.display()
            )
        })?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .with_context(|| format!("failed to open host broker audit log at {}", path.display()))?;
    let line =
        serde_json::to_string(entry).context("failed to serialize host broker audit entry")?;
    writeln!(file, "{line}").context("failed to append host broker audit log")?;
    Ok(())
}

pub fn summarize_args(value: &Value) -> Value {
    summarize_value(value, 0)
}

fn summarize_value(value: &Value, depth: usize) -> Value {
    if depth >= 3 {
        return Value::String("[redacted-depth]".to_string());
    }
    match value {
        Value::Object(map) => {
            let mut summarized = Map::new();
            for (key, entry) in map {
                let normalized = key.to_ascii_lowercase();
                if should_redact_key(&normalized) {
                    summarized.insert(key.clone(), Value::String("[redacted]".to_string()));
                    continue;
                }
                summarized.insert(key.clone(), summarize_value(entry, depth + 1));
            }
            Value::Object(summarized)
        }
        Value::Array(items) => Value::Array(
            items
                .iter()
                .take(20)
                .map(|item| summarize_value(item, depth + 1))
                .collect(),
        ),
        Value::String(text) => {
            if looks_sensitive_text(text) {
                Value::String("[redacted]".to_string())
            } else if text.len() > 160 {
                Value::String(format!("{}...", &text[..160]))
            } else {
                Value::String(text.clone())
            }
        }
        other => other.clone(),
    }
}

fn should_redact_key(key: &str) -> bool {
    matches!(
        key,
        "approval_token"
            | "token"
            | "authorization"
            | "cookie"
            | "cookies"
            | "clipboard"
            | "content"
            | "text"
            | "value"
            | "data_url"
            | "base64"
            | "file_contents"
    )
}

fn looks_sensitive_text(value: &str) -> bool {
    let trimmed = value.trim();
    trimmed.starts_with("data:") || trimmed.starts_with("-----BEGIN") || trimmed.len() > 400
}
