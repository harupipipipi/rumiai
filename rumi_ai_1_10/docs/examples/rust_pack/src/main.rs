//! Rumi AI OS — Rust Pack サンプル
//!
//! このサンプルは 2 つの機能を提供します:
//!   - hello: 挨拶を返す
//!   - kv_store: インメモリ KV ストア（1 回の呼び出しで get/set/delete/list を処理）
//!
//! stdin/stdout JSON プロトコルに従い、Kernel からの入力を受け取り、
//! 処理結果を JSON で返します。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{self, Read};

// --- 入力構造体 ---

#[derive(Deserialize)]
struct Input {
    context: Context,
    args: serde_json::Value,
}

#[derive(Deserialize)]
struct Context {
    principal_id: String,
    pack_id: String,
    function_id: String,
    #[allow(dead_code)]
    request_id: String,
    ts: String,
}

// --- 出力構造体 ---

#[derive(Serialize)]
struct HelloOutput {
    message: String,
    greeted_by: String,
    principal: String,
    timestamp: String,
}

#[derive(Serialize)]
struct KvOutput {
    action: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    value: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    entries: Option<HashMap<String, serde_json::Value>>,
    success: bool,
}

#[derive(Serialize)]
struct ErrorOutput {
    error: String,
    error_type: String,
}

// --- メイン ---

fn main() {
    // stdin から全文読み取り
    let mut input_str = String::new();
    if let Err(e) = io::stdin().read_to_string(&mut input_str) {
        eprintln!("Failed to read stdin: {}", e);
        std::process::exit(1);
    }

    // JSON パース
    let input: Input = match serde_json::from_str(&input_str) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Failed to parse input JSON: {}", e);
            std::process::exit(1);
        }
    };

    // function_id に応じて処理を分岐
    let result = match input.context.function_id.as_str() {
        "hello" => handle_hello(&input),
        "kv_store" => handle_kv_store(&input),
        _ => {
            let err = ErrorOutput {
                error: format!("Unknown function_id: {}", input.context.function_id),
                error_type: "unknown_function".to_string(),
            };
            match serde_json::to_string(&err) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("Failed to serialize error: {}", e);
                    std::process::exit(1);
                }
            }
        }
    };

    // stdout に結果を出力
    println!("{}", result);
}

fn handle_hello(input: &Input) -> String {
    let name = input
        .args
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("World");

    let output = HelloOutput {
        message: format!("Hello, {}!", name),
        greeted_by: format!(
            "{}:{}",
            input.context.pack_id, input.context.function_id
        ),
        principal: input.context.principal_id.clone(),
        timestamp: input.context.ts.clone(),
    };

    match serde_json::to_string(&output) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to serialize output: {}", e);
            std::process::exit(1);
        }
    }
}

fn handle_kv_store(input: &Input) -> String {
    let action = input
        .args
        .get("action")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    let output = match action {
        "set" => {
            let key = input
                .args
                .get("key")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();
            let value = input.args.get("value").cloned();

            KvOutput {
                action: "set".to_string(),
                key: Some(key),
                value,
                entries: None,
                success: true,
            }
        }
        "get" => {
            let key = input
                .args
                .get("key")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();

            // 注: これはサンプルのため、実際にはストレージに保存されない
            // 実用的な実装ではファイルや DB を使用する
            KvOutput {
                action: "get".to_string(),
                key: Some(key),
                value: None,
                entries: None,
                success: true,
            }
        }
        "list" => KvOutput {
            action: "list".to_string(),
            key: None,
            value: None,
            entries: Some(HashMap::new()),
            success: true,
        },
        "delete" => {
            let key = input
                .args
                .get("key")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();

            KvOutput {
                action: "delete".to_string(),
                key: Some(key),
                value: None,
                entries: None,
                success: true,
            }
        }
        _ => {
            eprintln!("Unknown action: {}", action);
            std::process::exit(1);
        }
    };

    match serde_json::to_string(&output) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to serialize output: {}", e);
            std::process::exit(1);
        }
    }
}
