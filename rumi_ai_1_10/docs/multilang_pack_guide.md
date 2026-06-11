<!-- docs-i18n-links:start -->
[EN](./multilang_pack_guide.md) | [JP](./i18n/ja/multilang_pack_guide.md) | [KR](./i18n/ko/multilang_pack_guide.md) | [CN](./i18n/zh-cn/multilang_pack_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Multilingual Pack Development Guide

Last updated: 2026-03-23

This document is a guide for developing Rumi AI OS Packs in languages other than Python (Rust, Go, Node.js, C/C++, etc.). Contains specifications, tutorials, and best practices for the stdin/stdout JSON protocol.

---

## 1. Multilingual Pack Overview

Rumi AI OS's capability_executor.py implements two calling_conventions: `binary` and `command`. Both use a common protocol: passing JSON on stdin and reading JSON from stdout.

This allows you to implement Pack's Functions in any language that can read and write JSON on stdin/stdout.

### binary vs command

| characteristics | binary | command |
|------|--------|---------|
| How to run | Directly run the compiled binary | Start the process with a command list |
| Suitable languages | Rust, Go, C, C++ | Node.js, Ruby, Python (different versions), shell scripting |
| Specifying ecosystem.json | `"runtime": "binary"`, `"main": "path/to/binary"` | `"runtime": "command"`, `"command": ["node", "index.js"]` |
| FunctionEntry field | `main_binary_path` | `command` (List[str]) |
| Path traversal verification | Yes (verifies whether binary is in function_dir) | Depends on command |

---

## 2. runtime section specifications

You can declare the information needed to build and run a multilingual pack by adding a `runtime` section to ecosystem.json.

```json
{
  "pack_id": "my_rust_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Rust Pack",
    "description": "Rust で実装された Pack"
  },
  "runtime": {
    "type": "binary",
    "build": {
      "command": "cargo build --release",
      "output": "target/release/my_binary"
    },
    "binary": "target/release/my_binary"
  }
}
```

### runtime field

| Field | Type | Description |
|-----------|-----|------|
| type | string | `"binary"` / `"command"` / `"python"` |
| build.command | string | build command |
| build.output | string | Build artifact path |
| binary | string | Path of the binary to be executed (when type=binary) |

---

## 3. stdin/stdout JSON protocol specification

### 3.1 Input (stdin)

When the Kernel starts the Function, it passes the following JSON to stdin.

```json
{
  "context": {
    "principal_id": "user_abc123",
    "pack_id": "my_pack",
    "function_id": "my_function",
    "request_id": "req_xyz789",
    "ts": "2026-03-23T12:00:00Z"
  },
  "args": {
    "key": "value",
    "count": 42
  }
}
```

#### context field

| Field | Type | Description |
|-----------|-----|------|
| principal_id | string | ID of the principal that issued the request (from UDS) |
| pack_id | string | ID of the Pack to which the executed Function belongs |
| function_id | string | ID of the Function to be executed |
| request_id | string | Unique ID of the request |
| ts | string | Request timestamp (ISO 8601, UTC) |

#### args field

A dictionary of arguments specified by the caller. The contents vary depending on the Function. Follows the structure defined in `input_schema`.

### 3.2 Output (stdout) — on success

Function outputs the processing result to stdout as JSON.

```json
{
  "message": "Hello, Pack!",
  "processed_at": "2026-03-23T12:00:01Z"
}
```

The output JSON is stored as is in `CapabilityResponse.output`. If the output is empty (nothing written to stdout), `output` becomes `null`.

### 3.3 Output (stderr) — on error

If an error occurs, exit with a non-zero exit code. The content written to stderr is recorded as an error message (up to the first 500 characters).

```
# 正常終了: exit code 0 + stdout に JSON
# エラー:  exit code 1 + stderr にメッセージ
```

**Important**: There is also a way to output error information to stdout as JSON, but the Kernel determines success/failure using the exit code. For non-zero exit code, stdout is ignored and stderr is used as the error message.

### 3.4 Timeout

| Setting | Value | Source |
|------|-----|--------|
| Default timeout | 30 seconds | `DEFAULT_FUNCTION_TIMEOUT = 30.0` |
| Maximum timeout | 120 seconds | `MAX_TIMEOUT = 120.0` |
| Minimum timeout | 1 second | `max(t, 1.0)` |
| Customization | Specified in `grant_config.timeout` of the Function manifest |

If the timeout is reached, the process is killed and a CapabilityResponse of `error_type: "timeout"` is returned.

### 3.5 Response size limit

Output on stdout must be less than or equal to **1 MB** (`MAX_RESPONSE_SIZE = 1 * 1024 * 1024` bytes). If it is exceeded, it will result in a `error_type: "response_too_large"` error.

---

## 4. calling_convention: binary details

### 4.1 Overview

This method directly executes the compiled binary. Suitable for languages ​​such as Rust, Go, C, and C++.

### 4.2 Execution flow

```
Kernel
  │
  ├─ 1. entry.main_binary_path の存在確認
  ├─ 2. パストラバーサル検証
  │     Path(binary_path).resolve().is_relative_to(func_dir)
  ├─ 3. タイムアウト取得
  ├─ 4. context + args の JSON 構築
  ├─ 5. subprocess.run([str(binary_path)],
  │       input=input_json,
  │       capture_output=True,
  │       text=True,
  │       timeout=timeout,
  │       cwd=str(func_dir))
  ├─ 6. exit code チェック
  │     ├─ 非ゼロ → エラー（stderr を使用）
  │     └─ ゼロ → stdout パース
  ├─ 7. stdout サイズチェック（1MB 制限）
  ├─ 8. stdout が空 → output=null
  └─ 9. JSON パース → CapabilityResponse(success=True, output=...)
```

### 4.3 ecosystem.json configuration example

```json
{
  "pack_id": "my_rust_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Rust Pack",
    "description": "Rust で実装されたサンプル Pack"
  },
  "runtime": {
    "type": "binary",
    "build": {
      "command": "cargo build --release",
      "output": "target/release/my_rust_function"
    }
  }
}
```

Function manifest (in the functions section):
```json
{
  "my_function": {
    "description": "サンプル Function",
    "runtime": "binary",
    "main": "my_binary",
    "calling_convention": "binary",
    "input_schema": {
      "type": "object",
      "properties": {
        "name": { "type": "string" }
      }
    },
    "grant_config": {
      "timeout": 30
    }
  }
}
```

### 4.4 Security

- **Path traversal prevention**: Verifies that the result of `resolve()` on a binary path is under `function_dir`. If you try to go outside function_dir with `../../` etc., a `security_violation` error will occur.
- **Working directory**: The process's cwd is set to `function_dir`.

---

## 5. calling_convention: command details

### 5.1 Overview

This method starts processes using a command list. Suitable for interpreted languages ​​(Node.js, Ruby, different versions of Python, etc.).

### 5.2 Execution flow

Uses the same stdin/stdout JSON protocol as `binary`. The difference is that we use `entry.command`(List[str]) as the process command instead of the binary path.

### 5.3 ecosystem.json configuration example

```json
{
  "pack_id": "my_node_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Node.js Pack",
    "description": "Node.js で実装されたサンプル Pack"
  },
  "runtime": {
    "type": "command",
    "build": {
      "command": "npm install"
    }
  }
}
```

Function manifest:
```json
{
  "my_function": {
    "description": "サンプル Function",
    "runtime": "command",
    "command": ["node", "index.js"],
    "calling_convention": "command",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": { "type": "string" }
      }
    }
  }
}
```

---

## 6. Security constraints

### 6.1 Path traversal prevention (binary)

`_execute_binary_function` performs the following validations:

```python
func_dir = Path(entry.function_dir).resolve()
if not Path(binary_path).resolve().is_relative_to(func_dir):
    # security_violation エラー
```

Be sure to place the binaries in the Pack's function_dir. Escapes via symbolic links or `../` are detected.

### 6.2 Response size limit

If the stdout output exceeds 1 MB, the response is discarded and a `response_too_large` error occurs. If you need to return large amounts of data, write it out to a file and return a path, or implement pagination.

### 6.3 Timeout

The Function must complete within a maximum of 120 seconds. The process will be killed when the timeout is reached. Consider asynchronous patterns (such as job queues) for processes that require long execution times.

### 6.4 Environment variables

`RUMI_PACK_ID` and `RUMI_FUNCTION_ID` are passed as environment variables to the Python Function executed in Docker. These are not passed to the binary/command Function. Get the necessary information from stdin's `context`.

---

## 7. Rust Pack Tutorial

### 7.1 Prerequisites

- Rust toolchain installed (`rustup` + `cargo`)
- Environment where Rumi AI OS operates

### 7.2 Project creation

```bash
mkdir -p my_rust_pack/functions/hello
cd my_rust_pack/functions/hello
cargo init --name hello_pack
```

### 7.3 Adding dependent crates

`Cargo.toml`:
```toml
[package]
name = "hello_pack"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

### 7.4 Implementation

`src/main.rs`:
```rust
use serde::{Deserialize, Serialize};
use std::io::{self, Read};

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
    request_id: String,
    ts: String,
}

#[derive(Serialize)]
struct Output {
    message: String,
    greeted_by: String,
    principal: String,
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap_or_else(|e| {
        eprintln!("Failed to read stdin: {}", e);
        std::process::exit(1);
    });

    let parsed: Input = serde_json::from_str(&input).unwrap_or_else(|e| {
        eprintln!("Failed to parse input JSON: {}", e);
        std::process::exit(1);
    });

    let name = parsed.args.get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("World");

    let output = Output {
        message: format!("Hello, {}!", name),
        greeted_by: format!("{}:{}", parsed.context.pack_id, parsed.context.function_id),
        principal: parsed.context.principal_id,
    };

    println!("{}", serde_json::to_string(&output).unwrap());
}
```

### 7.5 Build

```bash
cargo build --release
```

### 7.6 Test

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_rust_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./target/release/hello_pack
```

Expected output:
```json
{"message":"Hello, Rumi!","greeted_by":"my_rust_pack:hello","principal":"test_user"}
```

### 7.7 ecosystem.json

```json
{
  "pack_id": "my_rust_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Rust Pack",
    "description": "Rust で実装された Hello Pack"
  },
  "runtime": {
    "type": "binary",
    "build": {
      "command": "cargo build --release",
      "output": "functions/hello/target/release/hello_pack"
    }
  }
}
```

### 7.8 Placement

Place the Pack directory in `ecosystem/` of Rumi AI OS by copying or symbolic linking the prebuilt binaries into function_dir.

---

## 8. Go Pack Tutorial

### 8.1 Prerequisites

- Go installed (1.21 or higher recommended)

### 8.2 Project creation

```bash
mkdir -p my_go_pack/functions/hello
cd my_go_pack/functions/hello
go mod init hello_pack
```

### 8.3 Implementation

`main.go`:
```go
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "os"
)

type Context struct {
    PrincipalID string `json:"principal_id"`
    PackID      string `json:"pack_id"`
    FunctionID  string `json:"function_id"`
    RequestID   string `json:"request_id"`
    Ts          string `json:"ts"`
}

type Input struct {
    Context Context                `json:"context"`
    Args    map[string]interface{} `json:"args"`
}

type Output struct {
    Message   string `json:"message"`
    GreetedBy string `json:"greeted_by"`
    Principal string `json:"principal"`
}

func main() {
    data, err := io.ReadAll(os.Stdin)
    if err != nil {
        fmt.Fprintf(os.Stderr, "Failed to read stdin: %v", err)
        os.Exit(1)
    }

    var input Input
    if err := json.Unmarshal(data, &input); err != nil {
        fmt.Fprintf(os.Stderr, "Failed to parse input JSON: %v", err)
        os.Exit(1)
    }

    name := "World"
    if v, ok := input.Args["name"]; ok {
        if s, ok := v.(string); ok {
            name = s
        }
    }

    output := Output{
        Message:   fmt.Sprintf("Hello, %s!", name),
        GreetedBy: fmt.Sprintf("%s:%s", input.Context.PackID, input.Context.FunctionID),
        Principal: input.Context.PrincipalID,
    }

    enc := json.NewEncoder(os.Stdout)
    if err := enc.Encode(output); err != nil {
        fmt.Fprintf(os.Stderr, "Failed to encode output: %v", err)
        os.Exit(1)
    }
}
```

### 8.4 Build and test

```bash
go build -o hello_pack .
echo '{"context":{"principal_id":"test_user","pack_id":"my_go_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./hello_pack
```

---

## 9. Node.js Pack Tutorial

### 9.1 Prerequisites

- Node.js installed (18+ recommended)

### 9.2 Project creation

```bash
mkdir -p my_node_pack/functions/hello
cd my_node_pack/functions/hello
npm init -y
```

### 9.3 Implementation

`index.js`:
```javascript
'use strict';

process.stdin.setEncoding('utf8');

let inputData = '';

process.stdin.on('data', (chunk) => {
    inputData += chunk;
});

process.stdin.on('end', () => {
    try {
        const input = JSON.parse(inputData);
        const context = input.context || {};
        const args = input.args || {};

        const name = args.name || 'World';

        const output = {
            message: 'Hello, ' + name + '!',
            greeted_by: context.pack_id + ':' + context.function_id,
            principal: context.principal_id,
        };

        process.stdout.write(JSON.stringify(output));
    } catch (e) {
        process.stderr.write('Error: ' + e.message);
        process.exit(1);
    }
});
```

### 9.4 Test

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_node_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | node index.js
```

### 9.5 ecosystem.json

```json
{
  "pack_id": "my_node_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Node.js Pack",
    "description": "Node.js で実装された Hello Pack"
  },
  "runtime": {
    "type": "command",
    "build": {
      "command": "npm install"
    }
  }
}
```

---

## 10. Debugging method

### 10.1 Testing on the command line

All multilingual Pack Functions follow the stdin/stdout protocol, so you can test them directly on the command line:

```bash
# テスト入力 JSON を作成
cat > /tmp/test_input.json << 'TESTEOF'
{
  "context": {
    "principal_id": "debug_user",
    "pack_id": "my_pack",
    "function_id": "my_func",
    "request_id": "debug_001",
    "ts": "2026-03-23T00:00:00Z"
  },
  "args": {
    "name": "Debug"
  }
}
TESTEOF

# バイナリ Function をテスト
cat /tmp/test_input.json | ./my_binary

# コマンド Function をテスト
cat /tmp/test_input.json | node index.js

# 出力を jq で整形
cat /tmp/test_input.json | ./my_binary | jq .
```

### 10.2 Check exit code

```bash
cat /tmp/test_input.json | ./my_binary
echo "Exit code: $?"
```

### 10.3 Checking stderr

```bash
cat /tmp/test_input.json | ./my_binary 2>/tmp/stderr.log
cat /tmp/stderr.log
```

### 10.4 Simulating timeouts

```bash
timeout 30 sh -c 'cat /tmp/test_input.json | ./my_binary'
echo "Exit code: $?"
```

### 10.5 Checking the response size

```bash
cat /tmp/test_input.json | ./my_binary | wc -c
# 1048576 (1MB) 以下であることを確認
```

---

## 11. Best Practices

### 11.1 Error handling

- When reading stdin fails, write a message to stderr and exit with exit code 1.
- Similarly when there is a JSON parsing error, stderr + exit code 1
- Errors during processing also include stderr + non-zero exit code
- Avoid panics/crashes (Rust recommends error handling instead of `unwrap()`)

### 11.2 Output

- If successful, output valid JSON in one line to stdout
- Don't mix extra line breaks or logs into stdout (use stderr)
- Mixing debug output with stdout results in JSON parsing error
- Keep output size below 1 MB

### 11.3 Performance

- Shorten startup time (timeout includes startup time)
- Large amounts of data are processed in batches instead of streaming (stdin is passed all at once)
- Rust/Go optimizes binary size with static linking

### 11.4 Security

- Do not read sensitive information from environment variables (get it from context)
- File access is limited to function_dir
- External network access declares appropriate permissions with requires
- Don't trust user input (args). perform validation

### 11.5 Cross-platform

- Rust: `cross` Cross-compiled in crate
- Go: `GOOS` / `GOARCH` Cross-compile with environment variables
- Node.js: Beware of platform-dependent native modules
- Do not include the extension in the binary name (unnecessary on non-Windows)

### 11.6 Test

- Prepare test input JSON in CI/CD and compare it with expected output
- Test multiple args patterns
- Also test for edge cases such as empty args, malformed JSON, and large inputs
- Make sure the exit code is correct

---

## Appendix A: Protocol Quick Reference

```
┌─────────────────────────────────────────────────┐
│                    Kernel                        │
│                                                  │
│  1. FunctionEntry を取得                          │
│  2. Trust/Grant 検証                              │
│  3. input_json = {"context": {...}, "args": {...}}│
│  4. subprocess.run(                              │
│       [binary_path] or command,                  │
│       input=input_json,                          │
│       timeout=30~120s,                           │
│       cwd=function_dir                           │
│     )                                            │
│  5. exit code → 0: 成功 / 非0: エラー             │
│  6. stdout (≤1MB) → JSON parse → output          │
│  7. stderr → エラーメッセージ (先頭500文字)         │
│                                                  │
└──────────┬──────────────────────────┬─────────────┘
           │ stdin (JSON)             │ stdout (JSON)
           ▼                         │
┌─────────────────────────────────────────────────┐
│              Function (任意の言語)                 │
│                                                  │
│  1. stdin から全文読み取り                         │
│  2. JSON パース → context, args                   │
│  3. 処理実行                                      │
│  4. 結果を JSON で stdout に出力                   │
│  5. exit code 0 で終了                            │
│                                                  │
│  エラー時:                                        │
│  1. stderr にメッセージ                            │
│  2. 非ゼロ exit code で終了                        │
└─────────────────────────────────────────────────┘
```

---

## Appendix B: CapabilityResponse field correspondence table

| Function behavior | CapabilityResponse |
|----------------|-------------------|
| exit 0 + JSON to stdout | `success=true, output=<parsed JSON>` |
| exit 0 + stdout empty | `success=true, output=null` |
| exit 0 + stdout is invalid JSON | `success=false, error_type="invalid_json_output"` |
| exit 0 + stdout > 1MB | `success=false, error_type="response_too_large"` |
| exit non-zero | `success=false, error_type="function_execution_error"` |
| Timeout | `success=false, error_type="timeout"` |
| Binary not found | `success=false, error_type="binary_not_found"` |
| Path traversal detection | `success=false, error_type="security_violation"` |

---

## Related documents

- [Pack Development Guide](./pack-development.md) — Overview of Pack
- [Sample Code: Rust Pack](examples/rust_pack/) — Complete sample of Rust Pack
- [Sample Code: Go Pack](examples/go_pack/) — Complete Go Pack sample
- [Sample Code: Node.js Pack](examples/node_pack/) — Complete sample of Node.js Pack
