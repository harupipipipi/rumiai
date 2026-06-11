<!-- docs-i18n-links:start -->
[EN](./pack_development_guide.md) | [JP](./i18n/ja/pack_development_guide.md) | [KR](./i18n/ko/pack_development_guide.md) | [CN](./i18n/zh-cn/pack_development_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Pack Development Guide

> **Legacy Document**: Retained for compatibility reference. New references should take precedence over [pack-development.md](./pack-development.md) and [pack-development-guide.md](./pack-development-guide.md).

Last updated: 2026-03-23

This document is a comprehensive guide for developing Rumi AI OS Packs. We cover Pack overview, structure, lifecycle, permission system, Docker isolation, and development workflow.

---

## 1. What is Pack?

A pack is a functional extension unit of Rumi AI OS. Packs add unique functions on top of the core functions provided by the OS itself (Kernel).

A Pack can contain the following elements:

- **Functions**: Processing units that can be called via API (JSON in → JSON out)
- **Components**: UI components and data models
- **Routes**: HTTP endpoint definition
- **Flows**: Workflow that combines multiple functions

Packs are defined by a manifest file called `ecosystem.json`. The Kernel reads this file, registers the Functions in the Pack with the FunctionRegistry, and makes them executable.

---

## 2. Pack structure

### 2.1 Directory structure

```
my_pack/
├── ecosystem.json          # Pack マニフェスト（必須）
├── functions/
│   ├── my_function/
│   │   ├── main.py         # Python Function のエントリーポイント
│   │   └── ...
│   └── my_binary_function/
│       ├── my_binary        # コンパイル済みバイナリ
│       └── ...
├── components/
│   └── ...
├── routes/
│   └── ...
└── flows/
    └── my_flow.flow.yaml
```

### 2.2 All fields in ecosystem.json

```json
{
  "pack_id": "my_pack",
  "pack_identity": "vendor:user/pack-name",
  "version": "1.0.0",
  "metadata": {
    "name": "My Pack",
    "description": "Pack の説明",
    "author": "Author Name",
    "license": "MIT",
    "is_core_pack": false
  },
  "vocabulary": {
    "types": []
  },
  "dependencies": {},
  "components": {},
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

| Field | Type | Required | Description |
|-----------|-----|------|------|
| pack_id | string | ✅ | Pack unique identifier |
| pack_identity | string | — | Formal identifier in vendor:user/name format |
| version | string | ✅ | Semantic versioning |
| metadata.name | string | ✅ | Human-readable Pack name |
| metadata.description | string | — | Pack description |
| metadata.author | string | — | Author name |
| metadata.license | string | — | License |
| metadata.is_core_pack | bool | — | Is core_pack (usually false) |
| vocabulary.types | array | — | Vocab type definition |
| dependencies | object | — | Other Packs that depend on |
| components | object | — | component definition |
| runtime | object | — | Runtime settings (for multilingual packs, see multilang_pack_guide.md for details) |

### 2.3 Function manifest

Each Function is defined in the `functions` section of ecosystem.json or in a manifest in the `functions/<function_id>/` directory.

Key fields in the Function manifest:

| Field | Type | Description |
|-----------|-----|------|
| description | string | Function description |
| runtime | string | `"python"` / `"binary"` / `"command"` |
| main | string | Binary relative path (when runtime=binary) |
| command | array[string] | Execution command (when runtime=command) |
| entrypoint | string | Python entry point (e.g. `"main.py:run"`) |
| calling_convention | string | Execution method (described later) |
| host_execution | bool | Execute directly on host |
| requires | array[string] | required permissions |
| caller_requires | array[string] | Permissions requested from caller |
| input_schema | object | Input JSON Schema |
| output_schema | object | Output JSON Schema |
| tags | array[string] | Search tags |
| vocab_aliases | array[string] | Vocab aliases |
| grant_config | object | Grant settings (timeout etc.) |
| docker_image | string | Docker image (default: python:3.11-slim) |
| extensions | object | extension metadata |

---

## 3. Pack lifecycle

Packs are managed through the following lifecycle:

### 3.1 Scan

The Kernel's PackImporter scans the Pack directory and reads `ecosystem.json`. Examine the structure of each Pack and discover its Function.

### 3.2 Approve

ApprovalManager manages the approval state of a Pack. Functions from unapproved packs cannot be executed. core_pack (where `pack_id` starts with the `core_` prefix) is automatically approved.

### 3.3 Load

Functions of the approved Pack will be registered in FunctionRegistry. For each Function:

1. Constructing FunctionEntry (reading fields from manifest)
2. Solving `main_py_path` / `main_binary_path` / `command` according to runtime
3. Path traversal verification (does the binary path fit within function_dir?)
4. Register with FunctionRegistry (qualified_name = `pack_id:function_id`)
5. Registering vocab_aliases

### 3.4 Execute

CapabilityExecutor is responsible for execution. The execution flow is as follows:

1. **FunctionRegistry resolution**: Search FunctionEntry by permission_id or qualified_name
2. **Trust Check**: Validate sha256 hash in TrustStore (core_pack is exempt)
3. **Grant check**: Verify principal × permission in GrantManager
4. **calling_convention branch**: Branch to the appropriate handler depending on the execution method of the Function
5. **Audit logging**: Record all execution results in the audit log

---

## 4. core_pack vs ecosystem Pack

### core_pack

- `pack_id` starts with `core_` prefix
- Included in Kernel
- Trust checks are simplified (sha256 is logged but verification in TrustStore is omitted)
- Automatically approved
- Placed in the `core_runtime/core_pack/` directory

### ecosystem Pack

- Packs developed by third parties or users
- Trust check is required (sha256 must be registered in TrustStore)
- Requires explicit approval
- Placed in the `ecosystem/` directory

---

## 5. Difference between Functions, Components, Routes, and Flows

### Functions

It is the most basic processing unit. Accepts JSON input and returns JSON output. Can be implemented in Python, compiled binaries, or commands.

### Components

Definition of UI components and data models. Provides structured data that can be shared between Packs.

### Routes

HTTP endpoint definition. It is registered with pack_api_server and provides an externally accessible API.

### Flows

This is a workflow that combines multiple functions. Defined in YAML and executed by Flow Engine. It can include conditional branches, loops, and error handling.

---

## 6. How Capability works

Rumi AI OS has a three-tier permission system:

### 6.1 Trust

TrustStore manages the sha256 hash of the handler file. If the registered hash and the run-time hash do not match, the execution is rejected. This detects file tampering.

### 6.2 Grant

GrantManager manages who (principal_id) and what (permission_id) can do. grant_config allows fine-grained control such as timeouts.

### 6.3 Rate Limit

Limits the number of calls per minute for a specific permission_id (e.g. `secrets.get`). The default is 60 times/minute/principal.

### 6.4 Capability Flow

```
リクエスト
  → FunctionRegistry 解決
  → Trust チェック（sha256 検証）
  → Grant チェック（principal × permission）
  → Rate Limit チェック（該当する場合）
  → calling_convention に応じた実行
  → 監査ログ記録
  → CapabilityResponse 返却
```

---

## 7. calling_convention (execution method)

calling_convention determines how the Function is executed.

| calling_convention | Description | Target language |
|-------------------|------|---------|
| kernel | Directly called from inside the kernel | — |
| subprocess | Run in Python subprocess | Python |
| block | DI-based handler for core_pack | Python |
| python_host | Run Python on the host process | Python |
| python_docker | Run Python inside a Docker container | Python |
| binary | Run compiled binary (stdin/stdout JSON) | Rust, Go, C/C++, etc. |
| command | Start a process with command list (stdin/stdout JSON) | Node.js, Ruby, arbitrary |

`binary` and `command` are the core of multilingual Pack development. For details, please refer to [Multilingual Pack Development Guide](./multilang_pack_guide.md).

---

## 8. How Docker isolation works

### 8.1 Overview

Python Functions from ecosystem packs (non-core_pack) run in Docker containers by default. This prevents any impact on the host system.

### 8.2 Docker execution flow

1. Write out the input JSON to a temporary file
2. Build a container with DockerRunBuilder
3. Mount function_dir with `/function:ro` (read-only)
4. Mount the input JSON file with `/input.json:ro`
5. Set environment variables `RUMI_PACK_ID`, `RUMI_FUNCTION_ID`
6. Run the Python runner script inside the container
7. Read JSON from stdout
8. Forcibly stop the container with `docker kill` when timeout occurs

### 8.3 If Docker is not available

If Docker is unavailable, it will fall back to a subprocess on the host (warning logs will be output).

### 8.4 Binary/Command Function Execution

Functions with calling_convention in `binary` and `command` run as subprocesses on the host rather than in Docker. However, in the case of `host_execution=false` and `runtime != "python"`, an error will occur as a security violation.

---

## 9. Development → Test → Distribution Workflow

### 9.1 Development

1. Create a Pack directory
2. Create `ecosystem.json`
3. Implement Function in the `functions/` directory
4. Create Flows, Components, and Routes as needed

### 9.2 Test

Function follows the JSON protocol for stdin/stdout, so you can test it directly on the command line:

```bash
# Python Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | python main.py

# バイナリ Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | ./my_binary

# コマンド Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | node index.js
```

### 9.3 Distribution

1. Distribute the Pack directory as a zip or publish it in a Git repository
2. User placed in `ecosystem/`
3. Kernel scans and registers at next startup
4. In the future, it will be distributed on the marketplace (Phase D/E)

---

## 10. CapabilityResponse

The results of every Function call are returned as a CapabilityResponse.

```json
{
  "success": true,
  "output": { "任意のデータ": "..." },
  "error": null,
  "error_type": null,
  "latency_ms": 42.5
}
```

| Field | Type | Description |
|-----------|-----|------|
| success | bool | Successful execution |
| output | any | Output data (JSON) |
| error | string / null | error message |
| error_type | string / null | error type |
| latency_ms | float | Time taken to execute (ms) |

### List of error types

| error_type | description |
|-----------|------|
| invalid_request | Invalid request format |
| handler_not_found | Handler not found |
| trust_denied | Trust check failed |
| grant_denied | Grant check failed |
| rate_limited | Rate limit reached |
| timeout | timeout |
| response_too_large | Response size exceeded (1MB) |
| function_execution_error | Error during Function execution |
| invalid_json_output | stdout is not valid JSON |
| binary_not_found | Binary not found |
| security_violation | Security violation (path traversal, etc.) |
| initialization_error | initialization error |
| internal_error | Internal error |

---

## Related documents

- [Multilingual Pack Development Guide](./multilang_pack_guide.md) — How to develop Packs in languages other than Python
- [Pack Desktop App Development Guide](./pack_desktop_app_guide.md) — How to develop a Pack for desktop apps
- [Roadmap](./roadmap.md) — Rumi AI OS overall plan
