use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HostBrokerStatus {
    pub enabled: bool,
    pub available: bool,
    pub status: String,
    pub url: Option<String>,
    pub connection_path: Option<String>,
    pub recovery: Option<String>,
}

impl HostBrokerStatus {
    pub fn disabled(reason: &str) -> Self {
        Self {
            enabled: false,
            available: false,
            status: "disabled".to_string(),
            url: None,
            connection_path: None,
            recovery: Some(reason.to_string()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HostBrokerConnectionInfo {
    pub version: u32,
    pub host: String,
    pub port: u16,
    pub url: String,
    pub token: String,
    pub permission_subject: String,
    pub pid: u32,
    pub created_at: u64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct HostBrokerComputerRunRequest {
    pub function_id: String,
    #[serde(default)]
    pub profile_id: Option<String>,
    #[serde(default)]
    pub pack_id: Option<String>,
    #[serde(default)]
    pub conversation_id: Option<String>,
    #[serde(default)]
    pub approval_token: Option<String>,
    #[serde(default)]
    pub args: Value,
}

#[derive(Debug, Clone, Serialize)]
pub struct HostBrokerError {
    pub code: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct HostBrokerComputerRunResponse {
    pub ok: bool,
    pub function_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<HostBrokerError>,
    pub audit_id: String,
}
