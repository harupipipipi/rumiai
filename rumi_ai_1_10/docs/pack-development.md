<!-- docs-i18n-links:start -->
[EN](./pack-development.md) | [JP](./i18n/ja/pack-development.md) | [KR](./i18n/ko/pack-development.md) | [CN](./i18n/zh-cn/pack-development.md)
<!-- docs-i18n-links:end -->

> **Quick Start Guide**: If you want to start Pack development, please refer to [Pack Development Quick Start Guide](./pack-development-guide.md).
# Rumi AI OS — Pack Development Guide

A guide for Pack developers. Please refer to [architecture.md](./architecture.md) for the overall design and [operations.md](./operations.md) for operational instructions.

---

## Table of Contents

1. [Development flow](#development-flow)
2. [Minimum configuration](#minimum-configuration)
3. [ecosystem.json](#ecosystemjson)
4. [blocks](#blocks)
5. [Type hints/validation](#type-hintsvalidation)
6. [Flow definition](#flow-definition)
7. [Flow → HTTP Response Mapping](#flow--http-response-mapping)
8. [Flow Modifier](#flow-modifier)
9. [Network Access](#network-access)
10. [context\["http\_request"\] Detailed specifications](#contexthttp_request-Detailed specifications)
11. [Using Secrets (from Pack)](#using-secrets-from-pack)
12. [Using Capability](#using-capabilities)
13. [Store API (via Capability)](#store-api-via-capability)
14. [Inter-Pack cooperation pattern](#inter-pack-cooperation-pattern)
15. [lib（install / update）](#libinstall--update)
16. [pip dependency (requirements.lock)](#pip-dependency-requirementslock)
17. [permissions.json](#permissionsjson)
18. [Including Capability Handler](#includes-capability-handler)
19. [vocab/converter (advanced)](#vocabconverter-advanced)
20. [Component (advanced)](#component-advanced)
21. [Pack-specific endpoint (routes.json)](#pack-specific-endpoint-routesjson)
22. [HTTP status code control](#http-status-code-control)
23. [Error Handling Best Practices](#error-handling-best-practices)
24. [Flow Modifier Recommended Pattern](#flow-modifier-recommended-pattern)
25. [Handler API classification](#handler-api-classification)
26. [Output key naming convention (details)](#output-key-naming-convention-details)
27. [Notes](#notes)
28. [API Reference](#api-reference)
29. [Tutorial: Creating a simple Pack](#tutorial-create-a-simple-pack)

---

## Development flow

### Step 0: Generate a template using a template

```bash
python -m core_runtime.pack_scaffold my-pack --template minimal --output-dir ecosystem/
```

Template type:
- `minimal`: Minimal configuration (ecosystem.json + run.py)
- `capability`: With Capability Handler
- `flow`: With Flow definition
- `full`: All included

1. **Create a Pack** — Place files in `ecosystem/<pack_id>/backend/`
2. **Write ecosystem.json** — Pack metadata (`pack_id`, `pack_identity` required)
3. **Write blocks/** — code called in `python_file_call`
4. **Write Flow** — Place in `user_data/shared/flows/` or `flows/` in Pack and connect blocks
5. **Get approval** — User approves the pack
6. **Execution** — After approval, blocks is called when executing the Flow

---

## Minimal configuration

```
ecosystem/my_pack/
└── backend/
    ├── ecosystem.json
    └── blocks/
        └── hello.py
```

> **About the path**: `ecosystem/<pack_id>/` is the recommended path. `ecosystem/packs/<pack_id>/` is also supported as a compatible path, but if the same `pack_id` exists in both, `ecosystem/<pack_id>/` takes precedence.

---

## ecosystem.json

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "version": "1.0.0",
  "description": "My first pack",
  "pack_identity_vocabulary": ["my_pack"]
}
```

| Field | Required | Description |
|-----------|------|------|
| `pack_id` | ✅ | Pack identifier. Match directory name |
| `pack_identity` | ✅ | Distributor identifier (e.g. `github:author/repo`). If this value changes during Pack update, apply will be rejected |
| `version` | Optional | Semantic Versioning |
| `description` | Optional | Description |
| `pack_identity_vocabulary` | Optional | List of vocabulary used by Pack. Used for collaboration with vocab.txt |
| `required_secrets` | Optional | List of required secret keys (e.g. `["OPENAI_API_KEY"]`). For providing information to users |
| `required_network` | Optional | Network requirements (e.g. `{"allowed_domains": ["api.example.com"], "allowed_ports": [443]}`). For providing information to users |
| `host_execution` | Optional | Need for host execution (`true` / `false`). For `true`, run as a host process instead of container isolation |

### connectivity (inter-pack dependency declaration)

You can declare dependencies between Packs by adding the `connectivity` field to `ecosystem.json`.

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "connectivity": {
    "provides": ["ai.client"],
    "requires": ["tool.registry"]
  }
}
```

| Field | Description |
|-----------|------|
| `provides` | List of service names provided by this Pack |
| `requires` | List of service names required by this Pack |

The connectivity `requires` / `provides` is used to automatically resolve the Pack load order (load_order) at startup. Packs that `provides` the services specified in `requires` are loaded first.

If manual specification (`load_order` field of `ecosystem.json`) exists, it will take precedence. Automatic resolution is applied only in the absence of manual specification.

Currently, the only runtime effect of connectivity is automatic load_order resolution. It may be expanded in the future.

#### Connectivity pattern example

| provides | Meaning | Typical Pack |
|----------|------|--------------|
| `ai.client` | AI API Client | OpenAI / Anthropic Client |
| `tool.registry` | Tool registration | Tool manager |
| `memory.store` | Memory Store | Memory Management |
| `ui.chat` | Chat UI | Frontend |

The provides / requires values are dot-separated free strings. The OS does not interpret the meaning of the value and only uses it for automatic resolution of load_order. Please match the names among pack developers.

---

## blocks

Python file called by `python_file_call`.

### Basic form

```python
# ecosystem/my_pack/backend/blocks/hello.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ（dict）
        context: 実行コンテキスト（dict）
            - flow_id: 実行中の Flow ID
            - step_id: 実行中のステップ ID
            - phase: 実行中のフェーズ名
            - ts: タイムスタンプ
            - owner_pack: 所有 Pack ID
            - inputs: 入力データ
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> dict
            - capability_socket: Capability UDS ソケットパス（存在する場合）

    Returns:
        JSON 互換の dict
    """
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

The `run` function also allows a one-argument version of `input_data` only.

### Return value

Please return a JSON compatible dict. The returned value is stored as is in the context key specified in the Flow's `output` field. The wrappers inside the Kernel (such as `_kernel_step_status`) are automatically removed, and the value returned by the block goes directly into `ctx[output_key]`.

### Output key naming convention

The following rules apply to the key name of the value stored in `output` of a Flow step.

Keys starting with the `_` prefix are reserved as Kernel internal keys. If the dict returned by `run()` of `python_file_call` contains keys with the `_` prefix (e.g. `_kernel_step_status`, `_debug`), they will be automatically excluded when stored in the `output` context of Flow.

Do not use the `_` prefix on output keys returned by Pack blocks. This may cause you to be unintentionally excluded.

```python
# NG: _ プレフィックスは除外される
def run(input_data, context=None):
    return {"_internal": "removed", "result": "kept"}
    # ctx に格納されるのは {"result": "kept"} のみ

# OK: プレフィックスなし
def run(input_data, context=None):
    return {"result": "kept", "metadata": {"source": "my_pack"}}
```

---

## Type hints/validation

### run() function signature

The `run()` function called by `python_file_call` accepts one of the following three patterns. The execution engine auto-detects the number of arguments in `inspect.signature`.

```python
# パターン1: 入力データとコンテキストの両方を受け取る（推奨）
def run(input_data: dict, context: dict) -> dict | None:
    ...

# パターン2: 入力データのみ受け取る
def run(input_data: dict) -> dict | None:
    ...

# パターン3: 引数なし
def run() -> dict | None:
    ...
```

### Type safety for input_data

`input_data` is the JSON serialized/deserialized value of the `input` field of the Flow definition. Therefore, the included types are limited to the following JSON-derived types:

| JSON type | Python type |
|---------|----------|
| object | `dict` |
| array | `list` |
| string | `str` |
| number (integer) | `int` |
| number (decimal) | `float` |
| boolean | `bool` |
| null | `None` |

`input_data` itself is usually `dict`, but if you specify a scalar value or list directly in the Flow definition, it will be of that type.

### context type

`context` is `dict[str, Any]`. The main keys are:

| Key | Type | Description |
|------|----|------|
| `flow_id` | `str` | Running Flow ID |
| `step_id` | `str` | Running step ID |
| `phase` | `str` | Execution phase name |
| `ts` | `str` | Execution start timestamp (ISO 8601 UTC) |
| `owner_pack` | `str \| None` | Owned Pack ID |
| `inputs` | `dict` | Same as input_data |
| `http_request` | `Callable` | HTTP request function (see [context\["http\_request"\] detailed specifications](#contexthttp_request-detailed specifications)) |
| `network_check` | `Callable` | Network access check function |
| `capability_socket` | `str \| None` | Capability UDS Socket Path |

### Return type

The return value of `run()` must be a JSON serializable value (`dict`, `list`, `str`, `int`, `float`, `bool`, `None`). If you return `None`, the Flow output will be treated as `null`. If the return value is `dict`, its contents are stored in the `output` variable of the Flow.

### Validation best practices

The contents of `input_data` are derived from external sources (Flow definitions and user input), so be sure to validate them.

```python
def run(input_data: dict, context: dict) -> dict:
    # 1. 型チェック（早期リターン）
    if not isinstance(input_data, dict):
        return {"error": "input_data must be a dict"}

    # 2. 必須フィールドの存在チェック
    url = input_data.get("url")
    if not url:
        return {"error": "missing required field: url"}

    # 3. 型の厳密チェック
    if not isinstance(url, str):
        return {"error": "field 'url' must be a string"}

    timeout = input_data.get("timeout", 30)
    if not isinstance(timeout, (int, float)):
        return {"error": "field 'timeout' must be a number"}

    # 4. 値の範囲チェック
    if timeout <= 0 or timeout > 120:
        return {"error": "field 'timeout' must be between 0 and 120"}

    # 5. 本処理
    result = context["http_request"](
        method="GET",
        url=url,
        timeout_seconds=timeout,
    )
    return {"result": result}
```

**Recommendation:**

- Instead of throwing an exception, return `{"error": "..."}` and exit normally.
- Check all required fields at the beginning of the function
- Check types strictly with `isinstance()`
- Set limits on numerical ranges and list lengths

---

## Flow definition

### Placement path

| Path | Purpose |
|------|------|
| `user_data/shared/flows/` | Share Flow. Suitable for wiring across multiple packs |
| `ecosystem/<pack_id>/backend/flows/` | Pack-specific Flow |

### Example

```yaml
# user_data/shared/flows/hello.flow.yaml

flow_id: hello
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "${ctx.name}"
    output: greeting
```

### How to write steps

#### python_file_call

```yaml
- id: generate_response
  phase: generate
  priority: 50
  type: python_file_call
  owner_pack: ai_client
  file: blocks/generate.py
  input:
    user_input: "${ctx.user_input}"
  output: ai_output
  timeout_seconds: 60
```

| Field | Required | Description |
|-----------|------|------|
| `id` | ✅ | Step ID (unique within the Flow) |
| `phase` | ✅ | Affiliation phase |
| `priority` | Optional | Execution priority (ascending order; default 100) |
| `type` | ✅ | `python_file_call` |
| `owner_pack` | Optional | Owned Pack (can be omitted if inferred from the path) |
| `file` | ✅ | Relative path of executable file |
| `input` | Any | Input data (variable expansion possible) |
| `output` | Optional | Output destination context key |
| `timeout_seconds` | Optional | Timeout seconds (default 60) |

#### handler

```yaml
- id: load_context
  phase: prepare
  priority: 10
  type: handler
  input:
    handler: "kernel:ctx.get"
    args:
      key: "context"
  output: context
```

The `handler` type directly calls the Kernel handler specified in `input.handler` (`kernel:*`) or the InterfaceRegistry registered handler. `input.args` is passed as an argument to the handler.

#### set

```yaml
- id: set_default
  phase: prepare
  priority: 5
  type: set
  input:
    key: "model"
    value: "gpt-4"
```

> **Note**: The `set` type is handled by the `flow.construct.set` handler registered in the InterfaceRegistry. The Flow loader interprets `set` as a standard step type, but execution is via construct. `set` If construct is not registered, the step is skipped.

#### flow (sub Flow call)

```yaml
- id: run_sub_pipeline
  phase: main
  priority: 50
  type: flow
  flow: sub_flow_id
  args:
    param1: "${ctx.value}"
  output: sub_result
```

The `flow` type calls another Flow as a sub-Flow. Recursive calls (circular references) are automatically detected and result in an error. The context of the sub Flow is deep copied from the parent and the values ​​specified in `args` are added.

#### function (Capability function call)

```yaml
- id: read_store
  phase: main
  priority: 50
  type: function
  function: store.get
  input:
    store_id: "my_store"
    key: "${ctx.key}"
  output: store_result
```

The `function` type executes the function registered in the FunctionRegistry via `capability_executor`. Specify `permission_id` (for example, `store.get`) in the `function` field. A corresponding Capability Grant is required for execution.

| Field | Required | Description |
|-----------|------|------|
| `type` | ✅ | `function` |
| `function` | ✅ | permission_id of the function to be executed (e.g. `store.get`, `docker.run`) |
| `input` | Any | Argument to the function (variable expansion possible) |
| `output` | Optional | Output destination context key |
| `vocab_normalize` | Optional | For `true`, vocab normalize the value of `function` before solving |

### Variable expansion

You can reference the value in context with `${ctx.key}`. Nested references (`${ctx.user.id}`) are also possible. If the reference does not exist, it will be `null`.

### Schedule execution

Regular execution is possible by adding the `schedule` field to the Flow.

#### cron expression (5 fields: minute, hour, day, month, day of the week)

```yaml
flow_id: daily_cleanup
schedule:
  cron: "0 0 * * *"

phases:
  - main
steps:
  # ...
```

#### interval (seconds specified, minimum 10 seconds)

```yaml
flow_id: health_check
schedule:
  interval: 30

phases:
  - main
steps:
  # ...
```

cron expressions support `*`, `*/N`, numeric, comma-separated, range (`N-M`), and range+step (`N-M/S`). The scheduler is evaluated in ticks every 10 seconds, so cron's precision is in minutes. Duplicate execution of the same Flow is automatically prevented.

### Flow control protocol

You can control the execution of the Flow by returning the `__flow_control` key in the block's return value.

#### Flow interruption

```python
def run(input_data, context=None):
    if not input_data.get("valid"):
        return {"__flow_control": "abort", "reason": "Invalid input"}
    return {"result": "ok"}
```

Returning `{"__flow_control": "abort", "reason": "..."}` interrupts the flow without executing any further steps. The reason for suspension is recorded in diagnostics.

> Currently, `__flow_control` only supports `"abort"`. Other values ​​are ignored.

---

## Flow → HTTP response mapping

When the endpoint defined in Pack's `routes.json` receives an HTTP request, the Pack API Server (`pack_api_server.py`) executes the corresponding Flow, converts the result into an HTTP response, and returns it.

### How response conversion works

In the current implementation, Flow execution results (`outputs`) are **always returned in JSON format**. Responses are generated via the `APIResponse` data class.

```python
@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
```

If the Flow runs successfully:

```json
{
  "success": true,
  "data": { "...Flow outputs がここに入る..." },
  "error": null
}
```

If the Flow execution fails:

```json
{
  "success": false,
  "data": null,
  "error": "エラーメッセージ"
}
```

### Status code

Pack API Server's `_send_response` uses the following HTTP status codes.

| Status | Status Code |
|------|-----------------|
| Flow execution successful | `200 OK` |
| Authentication failure | `401 Unauthorized` |
| Invalid input | `400 Bad Request` |
| Route not found | `404 Not Found` |
| Internal error | `500 Internal Server Error` |

### Header

The following headers are automatically added to the response.

| Header | Value | Condition |
|---------|-----|------|
| `Content-Type` | `application/json; charset=utf-8` | Always granted |
| `Access-Control-Allow-Origin` | Requested by Origin | Matches CORS allow list |
| `Vary` | `Origin` | When adding CORS header |

### Control with special keys

Direct control of HTTP responses using special keys such as `_status_code`, `_headers`, `_body` is **not supported** at this time. Flow outputs are always stored in the `data` field of `APIResponse` and returned in `application/json` format.

If you need custom status code or header control, see [HTTP Status Code Control](#http-status-code-control).

---

## Flow Modifier

This is a mechanism for inserting functions into an existing Flow later.

### Placement path

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/`

### Example

```yaml
# user_data/shared/flows/modifiers/add_logging.modifier.yaml

modifier_id: add_logging
target_flow_id: ai_response
phase: postprocess
priority: 90
action: inject_after
target_step_id: format_output

step:
  id: log_response
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log_ai_response.py
  input:
    response: "${ctx.response}"
```

### Available actions

| action | description |
|--------|------|
| `inject_before` | Insert before specified step |
| `inject_after` | Insert after specified step |
| `append` | Add to end of phase |
| `replace` | Replace specified step |
| `remove` | Delete specified step |

> **phase constraints**: Modifier's `phase` must be included in the target Flow's `phases` list. If you specify a phase that does not exist, the Modifier will be skipped.

> **Application order**: Modifiers are sorted by phase → priority → modifier_id and applied deterministically. If there are multiple modifiers at the same injection point (`inject_before` / `inject_after` to the same `target_step_id`), they are inserted all at once in the order of priority → step.id → modifier_id to prevent non-determinism due to index shift. `replace` / `remove` are applied before inject / append.

### Wildcard target_flow_id

You can use a wildcard pattern in `target_flow_id` to apply Modifiers to multiple Flows at the same time.

| Pattern | Meaning |
|----------|------|
| `*` | Applies to all Flows |
| `my_pack.*` | Applies to all Flows starting with `my_pack.` |

Python's `fnmatch` is used for matching.

```yaml
modifier_id: global_logging
target_flow_id: "*"
phase: postprocess
priority: 99
action: append
step:
  id: global_log
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log.py
```

### requires condition

```yaml
requires:
  interfaces:
    - "ai.client"
  capabilities:
    - "tool_support"
```

If the condition is not met, the Modifier will be skipped.

---

## Network access

### Overview

Packs are isolated in Docker `--network=none` and cannot communicate directly externally. A Network Grant is required for external communication, and all requests go through the Egress Proxy (UDS socket).

### HTTP requests inside blocks

```python
def run(input_data, context=None):
    http_request = context.get("http_request")
    if not http_request:
        return {"error": "http_request not available"}

    result = http_request(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": "Bearer ...",
            "Content-Type": "application/json"
        },
        body='{"model": "gpt-4", "messages": [...]}',
        timeout_seconds=30.0
    )

    if result["success"]:
        return {"data": result["body"]}
    else:
        return {"error": result["error"]}
```

> **Timeout limit**: The maximum value for `timeout_seconds` is 120 seconds. Any value greater than 120 will be truncated to 120 seconds. This limit applies to both `rumi_syscall` and `rumi_capability`.

### Pre-check access availability

```python
def run(input_data, context=None):
    check = context.get("network_check")
    result = check("api.openai.com", 443)

    if not result["allowed"]:
        return {"error": result["reason"]}

    # 通信可能
```

### How to get a grant

Granted by user or operator via API. For more information, see ``Network Permission Management'' in [operations.md](./operations.md).

---

## context["http_request"] Detailed specifications

The `context["http_request"]` passed in `run(input_data, context)` of `python_file_call` is the only means by which the Pack code has external HTTP communication.

### Function signature

```python
def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    ...
```

### Parameters

| Parameters | Type | Default | Description |
|------------|-----|-----------|------|
| `method` | `str` | (Required) | HTTP method. `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD` |
| `url` | `str` | (required) | Complete URL to request |
| `headers` | `dict[str, str] \| None` | `None` | HTTP request headers |
| `body` | `str \| None` | `None` | Request body (string). When sending JSON, pass the `json.dumps()` string |
| `timeout_seconds` | `float` | `30.0` | Timeout seconds. Limited to maximum `120.0` seconds |

### Return value

On success:

```python
{
    "success": True,
    "status_code": 200,          # int: HTTPステータスコード
    "headers": {"Content-Type": "application/json", ...},  # dict: レスポンスヘッダー
    "body": "...",               # str: レスポンスボディ
    "latency_ms": 123.4,         # float: 所要時間（ミリ秒）
    "redirect_hops": 0,          # int: リダイレクト回数
    "bytes_read": 1024,          # int: 読み取りバイト数
    "final_url": "https://...",  # str: 最終URL（リダイレクト後）
}
```

On failure:

```python
{
    "success": False,
    "error": "エラーメッセージ",     # str: エラー内容
    "error_type": "timeout",       # str: エラー種別
}
```

### error_type list

| error_type | description |
|------------|------|
| `socket_not_found` | Egress Proxy socket not found |
| `permission_denied` | No permission to access socket |
| `connection_refused` | Connection to Egress Proxy was refused |
| `timeout` | Request timed out |
| `syscall_error` | Protocol level error |
| `json_decode_error` | JSON parsing of response failed |
| `grant_denied` | Access denied due to Network Grant |

### Communication via UDS Egress Proxy

All external HTTP communication from the Pack code goes through the **UDS (Unix Domain Socket) Egress Proxy**. Pack code cannot do direct network communication.

Communication flow:

```
Pack コード (run関数)
  → context["http_request"]()
    → UDS ソケット (/run/rumi/egress/packs/{pack_id}.sock)
      → Egress Proxy (Kernel 側)
        → Network Grant Manager でアクセス許可を検証
          → 許可されていれば外部 HTTP リクエストを実行
          → 拒否されていれば grant_denied エラーを返却
```

> The socket path can be changed with the `RUMI_EGRESS_SOCK_DIR` environment variable. The default is `/run/rumi/egress/packs`.

### Difference between container mode and host mode

| Item | Container mode (strict) | Host mode (permissive) |
|------|--------------------------|---------------------------|
| Network | `--network=none` (Complete isolation) | Use host network |
| Communication path | Only via UDS socket | Via UDS socket (via helper function) |
| Socket path | `/run/rumi/egress/packs/{pack_id}.sock` (Inside container mount) | `{RUMI_EGRESS_SOCK_DIR}/{pack_id}.sock` |
| Grant Validated | Egress Proxy Validated | Egress Proxy Validated |
| Security | Docker Quarantine + UDS Restrictions | Run with warnings (not recommended for production) |

In container mode (`RUMI_SECURITY_MODE=strict`), the Docker container is started with `--network=none`, so there is no other means of communication other than UDS sockets. Host mode (`RUMI_SECURITY_MODE=permissive`) runs without Docker, but `context["http_request"]` also goes through the Egress Proxy, so control by Network Grant is effective.

### Usage example

```python
def run(input_data: dict, context: dict) -> dict:
    # GET リクエスト
    result = context["http_request"](
        method="GET",
        url="https://api.example.com/data",
        headers={"Accept": "application/json"},
        timeout_seconds=10.0,
    )

    if not result["success"]:
        return {"error": result["error"]}

    return {"status": result["status_code"], "body": result["body"]}
```

```python
def run(input_data: dict, context: dict) -> dict:
    import json

    # POST JSON リクエスト
    result = context["http_request"](
        method="POST",
        url="https://api.example.com/items",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"name": input_data.get("name")}),
        timeout_seconds=15.0,
    )

    if not result["success"]:
        return {"error": result["error"], "error_type": result.get("error_type")}

    return {"created": True, "response": result["body"]}
```

---

## Using Secrets (from Pack)

Packs use `secrets.get` Capability to obtain secrets (such as API keys). It becomes available after the operator registers Secrets and grants grants.

### Usage example

```python
import rumi_capability

result = rumi_capability.call("secrets.get", args={"key": "OPENAI_API_KEY"})
if result["success"]:
    api_key = result["output"]["value"]
else:
    # "Access denied or secret not found"
    error = result["output"]["error"]
```

### Access control

The `secrets.get` grant must explicitly specify a key that is accessible in `grant_config.allowed_keys`. If `allowed_keys` is empty or unspecified, access to all keys is denied (fail-closed).

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "my_pack",
    "permission_id": "secrets.get",
    "config": {"allowed_keys": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]}
  }'
```

### Important constraints

- `get` can only be obtained via Capability. No API exists to directly redisplay secret values
- Rate limit is applied to `secrets.get` (default 60 times/min/Pack, can be changed with environment variable `RUMI_SECRET_GET_RATE_LIMIT`, sliding window method)
- Values are never included in logs, audits, or exception messages
- Whether the key exists or not cannot be determined from the error message (unified by "Access denied or secret not found")

---

## Using Capabilities

For a Pack to use a capability handler (e.g. read the file system, run an external tool, etc.), the Pack must be granted the appropriate permission grant.

### Relationship between Trust and Grant

Capability requires two levels of approval.

1. **Trust registration** (handler authorization): Register handler's code (sha256) as trusted
2. **Grant** (permission grant): Grant permission of approved handler to Pack.

```
handler.py が信頼される（Trust 登録）
    ↓
Pack に permission が付与される（Grant 付与）
    ↓
Pack が capability を使用可能
```

Even if a Trust is registered, it cannot be used without a Grant. Conversely, even if there is a grant, a handler with no trust registered cannot be executed.

### How to call Capability

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})
if result["success"]:
    content = result["output"]
else:
    error = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
```

### Built-in Capability Handler

The following Capability Handlers are included in the core runtime and can be used without trust registration (separate grant required).

| permission_id | handler_id | description | risk |
|---------------|-----------|------|------|
| `secrets.get` | `core.secrets.get` | Get secret value | high |
| `store.get` | `core.store.get` | Reading value from Store | low |
| `store.set` | `core.store.set` | Writing value to Store | medium |
| `store.delete` | `core.store.delete` | Removing a value from a Store | medium |
| `store.list` | `core.store.list` | Get list of keys in Store | low |
| `store.batch_get` | `core.store.batch_get` | Bulk retrieval from Store (up to 100 keys) | low |
| `store.cas` | `core.store.cas` | Store Compare-And-Swap (optimistic exclusive control) | medium |
| `pack.inbox.send` | `core.communication.send` | Send JSON message to inbox of other Pack components | medium |
| `pack.update.propose_patch` | `core.communication.propose_patch` | Propose file changes to other Packs (staging creation, no automatic application) | high |
| `flow.run` | `core.flow.run` | Synchronous Flow-to-Flow calls | medium |
| `docker.run` | `core.docker.run` | Docker container execution | — |
| `docker.exec` | `core.docker.exec` | Command execution inside Docker container | — |
| `docker.stop` | `core.docker.stop` | Stopping Docker container | — |
| `docker.logs` | `core.docker.logs` | Docker container log acquisition | — |
| `docker.list` | `core.docker.list` | Docker container list | — |

### Grant Grant

Grants are granted by users or operators using the API. For more information, see ``Capability Grant Management'' in [operations.md](./operations.md).

```bash
# 例: store.get の Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["my_store"]}}'
```

### Grant configuration (grant_config)

Grants can have limits set in `config`. Settings differ depending on permission.

| permission_id | grant_config key | description |
|---------------|-------------------|------|
| `secrets.get` | `allowed_keys` | List of accessible key names (required, completely denied if empty) |
| `store.get/set/delete/list` | `allowed_store_ids` | List of accessible store_ids (required, completely rejected if empty) |
| `store.set` | `max_value_bytes` | Maximum write size (bytes, default 1MB) |

`allowed_keys` / `allowed_store_ids` are fail-closed. If the list is empty or unspecified, all access will be denied.

### Error handling

If the Capability call fails, a dict containing `success: False` is returned.

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})

if not result.get("success", False):
    error_type = result.get("error_type", "unknown")

    if error_type == "grant_denied":
        # Grant が付与されていない
        pass
    elif error_type == "trust_denied":
        # handler が信頼されていない
        pass
    elif error_type == "handler_not_found":
        # handler が存在しない
        pass
    elif error_type == "execution_error":
        # handler 実行中のエラー
        pass
    elif error_type == "timeout":
        # タイムアウト
        pass
```

| error_type | description |
|------------|------|
| `grant_denied` | Pack has no permission grant |
| `trust_denied` | sha256 of handler is not registered in Trust Store |
| `handler_not_found` | The handler corresponding to the specified permission_id does not exist |
| `execution_error` | Error while running handler |
| `timeout` | Execution timed out |
| `socket_not_found` | Capability socket not found |

---

## Store API (via Capability)

### Overview

A Store is a key-value store that can be shared between Packs. Store operations are performed via Capability. Access is enabled when an operator grants a Capability Grant to a pack.

### Available permission_id

| permission_id | description | args |
|---------------|------|------|
| `store.get` | Read value from Store | `store_id`, `key` |
| `store.set` | Write value to Store | `store_id`, `key`, `value` |
| `store.delete` | Remove value from Store | `store_id`, `key` |
| `store.list` | Get list of keys in Store | `store_id`, `prefix` (optional) |

### Usage example

```python
import rumi_capability

# 値の書き込み
result = rumi_capability.call("store.set", args={
    "store_id": "my_store",
    "key": "users/user_001",
    "value": {"name": "Alice", "role": "admin"}
})

# 値の読み取り
result = rumi_capability.call("store.get", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
if result["success"]:
    output = result["output"]
    if output.get("success"):
        user = output["value"]

# キー一覧
result = rumi_capability.call("store.list", args={
    "store_id": "my_store",
    "prefix": "users/"
})
```

> `output` of `store.list` contains `success` (bool) and `keys` (array of key names).

```python
# 値の削除
result = rumi_capability.call("store.delete", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
```

### Grant settings

Grants in `store.*` can have limits set in `grant_config`:

| grant_config key | Description | Default |
|-------------------|------|-----------|
| `allowed_store_ids` | List of store_ids to allow access | `[]` (If the list is empty, access to all Stores is denied. Store_id must be explicitly specified to access) |
| `max_value_bytes` | `store.set` maximum size (bytes) | 1MB (1048576) |

`allowed_store_ids` is fail-closed. If you do not specify `allowed_store_ids` or specify an empty list `[]` when creating a Grant, access to all Stores will be denied for that Grant. For a Pack to access a Store, the operator must explicitly add the store_id to the list.

### Create a Store

Store creation is done using the operational API:

```bash
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "my_store", "root_path": "user_data/stores/my_store"}'
```

> **store_id constraints**: `store_id` must match `^[a-zA-Z0-9_-]{1,64}$`.

### Built-in Capability Handler list

The following Capability Handlers are included in the core runtime and can be used without trust registration (separate grant required).

| permission_id | handler_id | description | risk |
|---------------|-----------|------|------|
| `secrets.get` | `core.secrets.get` | Get secret value | high |
| `store.get` | `core.store.get` | Reading value from Store | low |
| `store.set` | `core.store.set` | Writing value to Store | medium |
| `store.delete` | `core.store.delete` | Removing a value from a Store | medium |
| `store.list` | `core.store.list` | Get list of keys in Store | low |
| `store.batch_get` | `core.store.batch_get` | Bulk retrieval from Store (up to 100 keys) | low |
| `store.cas` | `core.store.cas` | Store Compare-And-Swap (optimistic exclusive control) | medium |
| `pack.inbox.send` | `core.communication.send` | Send JSON message to inbox of other Pack components | medium |
| `pack.update.propose_patch` | `core.communication.propose_patch` | Propose file changes to other Packs (staging creation, no automatic application) | high |
| `flow.run` | `core.flow.run` | Synchronous Flow-to-Flow calls | medium |
| `docker.run` | `core.docker.run` | Docker container execution | — |
| `docker.exec` | `core.docker.exec` | Command execution inside Docker container | — |
| `docker.stop` | `core.docker.stop` | Stopping Docker container | — |
| `docker.logs` | `core.docker.logs` | Docker container log acquisition | — |
| `docker.list` | `core.docker.list` | Docker container list | — |

---

## Inter-pack cooperation pattern

### Wiring with shared Flow

Blocks from multiple Packs can be connected using a Flow placed in `user_data/shared/flows/`. Packs do not need to know about each other.

```yaml
# user_data/shared/flows/ai_pipeline.flow.yaml
flow_id: ai_pipeline
phases:
  - prepare
  - generate
  - postprocess

steps:
  - id: load_capabilities
    phase: prepare
    priority: 50
    type: python_file_call
    owner_pack: capability_provider
    file: blocks/load_capabilities.py
    output: capabilities

  - id: generate
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      capabilities: "${ctx.capabilities}"
    output: response
```

### Data delivery via Store

Use Stores to share data between Packs working in different Flows.

```python
# Pack A: データを Store に書き込む
import rumi_capability

rumi_capability.call("store.set", args={
    "store_id": "shared_data",
    "key": "latest_result",
    "value": {"score": 0.95, "text": "..."}
})
```

```python
# Pack B: Store からデータを読み取る
import rumi_capability

result = rumi_capability.call("store.get", args={
    "store_id": "shared_data",
    "key": "latest_result"
})
if result["success"]:
    data = result["output"]["value"]
```

---

## lib（install / update）

### Overview

This is a script that is executed only once when the Pack is initialized or updated. It is not normally executed.

### File structure

```
ecosystem/<pack_id>/backend/lib/
├── install.py    # 初回導入時に実行
└── update.py     # ハッシュ変更時に実行（なければ install.py が実行される）
```

### install.py example

```python
def run(context=None):
    pack_id = context.get("pack_id") if context else "unknown"
    data_dir = context.get("data_dir") if context else None

    # data_dir 内に初期設定ファイルを作成
    if data_dir:
        import json, os
        config_path = os.path.join(data_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump({"initialized": True}, f)

    return {"status": "installed"}
```

### Information provided by context

| Key | Description |
|------|------|
| `pack_id` | Pack ID |
| `lib_type` | `"install"` or `"update"` |
| `ts` | Timestamp |
| `lib_dir` | lib directory path (inside container: `/lib`) |
| `data_dir` | Writable directory (in container: `/data`, host: `user_data/packs/{pack_id}/`) |

### Security constraints

In strict mode, it runs isolated inside a Docker container. `--network=none`, `--read-only`. Writing is possible only to `/data` (= `user_data/packs/{pack_id}/`).

---

## pip dependency (requirements.lock)

### Overview

If your pack depends on a PyPI package, include `requirements.lock`.

### Placement path

Searched in the following order:

1. `<pack_subdir>/requirements.lock`
2. `<pack_subdir>/backend/requirements.lock` (compatible)

### Format

Only the `NAME==VERSION` line is allowed. Comment lines and blank lines are allowed.

```
requests==2.31.0
flask==3.0.0
```

The following are prohibited: `-e`, `git+`, `http://`, `https://`, `file:`, `../`, `/`, `--` optional lines, `@` direct reference.

### Usage from Pack code

After approval and installation, just run `import` as usual.

```python
import requests  # pip で導入された依存

def run(input_data, context=None):
    resp = requests.get("https://api.example.com/data")
    return {"data": resp.json()}
```

In the execution container, site-packages are mounted as `/pip-packages:ro` and added to `PYTHONPATH`.

### How to get approval

User or operator approves via API. For more information, see ``pip dependency library management'' in [operations.md](./operations.md).

---

## permissions.json

A file that declares the permissions required by the Pack.

```json
{
  "pack_id": "my_pack",
  "permissions": [
    {
      "type": "network",
      "domains": ["api.example.com"],
      "ports": [443],
      "reason": "外部 API にアクセスするため"
    }
  ]
}
```

permissions.json is declarative and not enforced at runtime. Actual access control is done through Capability Grants and Network Grants. This file is for informational purposes to users (what permissions this Pack requires).

---

## Include Capability Handler

When a Pack provides a capability handler, it follows the following conventions:

### Placement

```
ecosystem/<pack_id>/
└── backend/
    └── share/
        └── capability_handlers/
            └── <slug>/
                ├── handler.json
                └── handler.py
```

Place it in `share/capability_handlers/<slug>/` under `pack_subdir` (usually `ecosystem/<pack_id>/backend/`) of the Pack.

### handler.json

```json
{
  "handler_id": "fs_read_handler",
  "permission_id": "fs.read",
  "entrypoint": "handler.py:execute",
  "description": "ファイルシステム読み取り handler",
  "risk": "ファイルシステムへの読み取りアクセスを提供"
}
```

| Field | Required | Description |
|-----------|------|------|
| `handler_id` | ✅ | Unique identifier of the handler |
| `permission_id` | ✅ | Requested permission ID |
| `entrypoint` | ✅ | Execution entry point (e.g. `handler.py:execute`) |
| `description` | Optional | Description |
| `risk` | Optional | Risk description |

Candidates are detected by scan, approved by the user, and copied to `user_data/capabilities/handlers/<slug>/`. Approve only registers Trust (sha256 allowlist), Grant is required separately.

> The above is the old method (compatible). The following functions/ method is recommended for the new Pack:

### functions/ method (recommended)

If your Pack provides Capability functions, place them in the `functions/` directory.

#### Placement

```
ecosystem/<pack_id>/
└── backend/
    └── functions/
        └── <function_id>/
            ├── manifest.json
            └── main.py
```

#### manifest.json

```json
{
  "function_id": "get",
  "description": "Read a value from a Store by key.",
  "requires": ["store.get"],
  "caller_requires": [],
  "host_execution": true,
  "tags": ["store", "read"],
  "risk": "low",
  "vocab_aliases": ["store.get"],
  "input_schema": {
    "type": "object",
    "required": ["store_id", "key"],
    "properties": {
      "store_id": { "type": "string" },
      "key": { "type": "string" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "success": { "type": "boolean" },
      "value": { "description": "The stored JSON value" }
    }
  },
  "calling_convention": "block"
}
```

| Field | Required | Description |
|-----------|------|------|
| `function_id` | ✅ | Function identifier |
| `description` | Optional | Function description |
| `requires` | ✅ | List of permission_ids required to run this function (e.g. `["store.get"]`) |
| `caller_requires` | Optional | List of additional privileges to request from the caller |
| `host_execution` | Optional | If `true`, run in the host process instead of the container |
| `tags` | Optional | List of classification tags |
| `risk` | Optional | Risk level (`low`, `medium`, `high`). It is omitted in some functions such as docker type |
| `vocab_aliases` | Optional | List of aliases used for vocab normalization |
| `input_schema` | Optional | Input JSON Schema |
| `output_schema` | Optional | Output JSON Schema |
| `grant_config` | Optional | Default settings for Grant (used in docker systems) |
| `calling_convention` | Optional | Calling convention. `block` (default, core_pack standard) = `execute(context, args)` Pattern |

> **Note**: The `permission_id` field does not exist in manifest.json. Use the `requires` array to specify permissions.

#### main.py

```python
def execute(context: dict, args: dict) -> dict:
    """
    Args:
        context: 実行コンテキスト
            - grant_config: Grant 設定（allowed_store_ids 等）
        args: 入力引数（manifest.json の input_schema に対応）

    Returns:
        JSON 互換の dict
    """
    store_id = args.get("store_id", "")
    key = args.get("key", "")

    # ... 処理 ...

    return {"success": True, "value": result}
```

If `calling_convention` is `block` (default), the entry point is `execute(context, args)`. `context` contains execution information such as `grant_config`, and `args` is passed the value specified in `input` of the Flow step.

---

## vocab/converter (advanced)

> There is no need to use it in normal Pack development. Advanced features for compatibility absorption.

### vocab.txt

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

Words written on the same line are treated as synonyms.

### converters

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

---

## Component (advanced)

Component is a unit with `components/{component_id}/manifest.json` and is used for lifecycle management (setup, etc.). `python_file_call` does not treat components specially, so please specify the relative path in the `file` field.

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

### Basic pattern of setup.py

The initialization process of Component is described in `components/{component_id}/setup.py`.

```python
# ecosystem/my_pack/backend/components/my_component/setup.py

def setup(context=None):
    """
    Component 初期化時に呼ばれる。

    Args:
        context: 実行コンテキスト
            - interface_registry: InterfaceRegistry
            - event_bus: EventBus
            - diagnostics: Diagnostics
            - install_journal: InstallJournal

    Returns:
        任意の値（diagnostics に記録される）
    """
    ir = context.get("interface_registry") if context else None
    if ir:
        ir.register("my_component.ready", True)
    return {"status": "initialized"}
```

setup is executed in the `kernel:component.load` step at startup.

---

## Pack-specific endpoint (routes.json)

### Overview

Packs can include `routes.json` to register their own endpoints on the HTTP API server. The received request executes the specified Flow and returns the result as a response.

### Placement path

`ecosystem/<pack_id>/backend/routes.json`

### routes.json format

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/api/my_pack/generate",
      "flow_id": "my_pack.generate",
      "description": "テキスト生成エンドポイント"
    },
    {
      "method": "GET",
      "path": "/api/orgs/{org_id}/tasks/{task_id}",
      "flow_id": "my_pack.get_task",
      "description": "タスク取得（パスパラメータ付き）"
    }
  ]
}
```

### Path parameters

Path parameters can be defined using the `{param}` notation. The path parameter values ​​are automatically included in the Flow's `inputs`.

Example: If you request `/api/orgs/{org_id}/tasks/{task_id}`, `inputs.org_id` and `inputs.task_id` will have their respective values.

### GET query parameters

Query parameters for GET requests are also included in `inputs`.

### Get Raw Body / Headers

Flow's `inputs` also includes the following special keys:

| Key | Description |
|------|------|
| `_raw_body` | base64 encoded value of request body |
| `_headers` | dict of request headers |
| `_method` | HTTP methods (GET, POST, etc.) |
| `_path` | Request path |

### Reload route

```bash
curl -X POST http://localhost:8765/api/routes/reload \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Check registered routes

```bash
curl http://localhost:8765/api/routes \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## HTTP status code control

### Current specifications

The current Pack API Server implementation **does not allow Pack to directly control the HTTP status code returned from the Pack's `routes.json` endpoint.

Even if you include a special key such as `_status_code` in the Flow's outputs, it will only be included in the `data` field of the response and will not be reflected in the HTTP status code.

### Status code determination logic

Pack API Server determines the status code using the following logic.

| Judgment order | Status | Status code |
|--------|------|-----------------|
| 1 | Authentication failure | `401` |
| 2 | Input validation failure | `400` |
| 3 | Route not found | `404` |
| 4 | Flow execution successful | `200` (fixed) |
| 5 | Error dict returned when running Flow | `200` (data contains error but HTTP is 200) |
| 6 | Exception occurs during Flow execution | `500` |

This means that even if the Flow completes successfully and returns `{"error": "not found"}`, the HTTP status code will be `200 OK`.

### Recommended pattern

Under current constraints, use the `success` and `error` fields in the response body to communicate errors to the client.

```python
def run(input_data: dict, context: dict) -> dict:
    item_id = input_data.get("id")
    if not item_id:
        return {"error": "missing id", "error_code": "MISSING_ID"}

    # ... 処理 ...

    if not found:
        return {"error": "item not found", "error_code": "NOT_FOUND"}

    return {"item": item_data}
```

On the client side, success/failure is determined by the presence or absence of `data.error`.

### Planned for future support

In a future version, we are considering adding the ability to recognize special keys (`_status_code`, `_headers`, etc.) in Flow outputs and reflect them in the HTTP response.

---

## Error handling best practices

### If an exception occurs in run() of python_file_call

`run()` When an uncaught exception occurs within a function, the execution engine does the following:

**Container mode**: The Docker process exits with a non-zero exit code and the contents of stderr are logged as an error message. `success` of `ExecutionResult` becomes `False`, and `error_type` becomes `"container_execution_error"`.**Host mode (permissive)**: The exception propagates from `Future` in `ThreadPoolExecutor`, and similarly `success` in `ExecutionResult` becomes `False`.

In either case, the Kernel's handler (`_h_python_file_call`) returns `_kernel_step_status: "failed"`.

### Recommended: wrap in try-except and return error dict

If you leak the exception, only the stack trace will be logged and no useful information will be passed to the calling Flow. Be sure to wrap it in try-except and return structured error information.

```python
def run(input_data: dict, context: dict) -> dict:
    try:
        url = input_data["url"]
        result = context["http_request"](
            method="GET",
            url=url,
            timeout_seconds=input_data.get("timeout", 30),
        )

        if not result["success"]:
            return {
                "error": result["error"],
                "error_type": result.get("error_type", "unknown"),
            }

        return {"data": result["body"], "status_code": result["status_code"]}

    except KeyError as e:
        return {"error": f"missing required field: {e}"}
    except Exception as e:
        return {"error": str(e), "error_type": type(e).__name__}
```

### Behavior when Flow step fails

The behavior when a step in a Flow fails is determined by the `defaults` and per-step `on_error` settings in the Flow definition.

| Settings | Behavior |
|------|------|
| `defaults.fail_soft: true` (default) | Record step failure and proceed to next step |
| `defaults.fail_soft: false` | Interrupt the entire Flow when a step fails |
| `on_error.action: "abort"` | Abort Flow if this step fails |
| `on_error.action: "continue"` | Continue even if this step fails |
| `on_error.action: "disable_target"` | Disable target and proceed |

If a Flow level error handler is registered in the InterfaceRegistry as `flow.error_handler`, that handler will be called when a step exception occurs. Error handlers can control behavior by returning `"abort"` (abort), `"retry"` (retry), or something else (continue).

### How to handle the return value in case of capability.call() failure

If you call Capability via the `rumi_capability` module, a dict containing `success: False` will be returned on failure.

```python
import rumi_capability

result = rumi_capability.call(
    "store.get",
    args={"store_id": "my_store", "key": "my_key"},
)

if not result.get("success", False):
    # エラー処理
    error_msg = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
    return {"error": error_msg, "error_type": error_type}

# 成功時の処理
value = result.get("output", {}).get("value")
```

Possible reasons for a Capability call to fail include:

| error_type | description |
|------------|------|
| `approval_denied` | Not authorized for use of Capability |
| `grant_denied` | Capability Grant not granted |
| `trust_denied` | Trust Store verification failed |
| `handler_not_found` | The specified Capability Handler does not exist |
| `execution_error` | An error occurred while running Handler |
| `timeout` | Execution timed out |
| `socket_not_found` | Capability socket not found |

We recommend that you check these errors using the `success` field of the return value instead of using try-except.

---

---

## Flow Modifier recommended pattern

Flow Modifier is a powerful feature, but it can be complicated if you try to use all actions from the beginning. We recommend starting with the following two patterns.

### Pattern 1: append (add to end of phase)

This is the safest and easiest to understand pattern. Add processing to the end without changing the existing Flow.

```yaml
modifier_id: add_logging
target_flow_id: ai_response
phase: postprocess
priority: 90
action: append

step:
  id: log_response
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log_response.py
  input:
    response: "${ctx.response}"
```

When to use: Add logging, auditing, notifications, and post-processing

### Pattern 2: replace (step replacement)

This is a pattern that replaces the implementation of an existing step. For example, use this when switching your AI client from OpenAI to Anthropic.

```yaml
modifier_id: swap_ai_client
target_flow_id: ai_response
phase: generate
priority: 50
action: replace
target_step_id: call_openai

step:
  id: call_anthropic
  type: python_file_call
  owner_pack: anthropic_client
  file: blocks/generate.py
  input:
    user_input: "${ctx.user_input}"
  output: ai_output
```

When to use: Replacing implementation, switching provider

### When to use inject_before / inject_after

inject_before / inject_after are used when you want to insert processing before and after a specific step. However, since it depends on the id of the target step, it is vulnerable to changes in the flow structure. Consider using it only if:

- If input data for a particular step needs to be pre-transformed (inject_before)
- If you need to post-process the output data of a particular step (inject_after)
- If the execution timing is too slow for append

### remove is a last resort

remove removes an existing step and can significantly change the behavior of the Flow. It is usually safer to provide an alternative implementation with replace.

---

## Handler API classification

There are two types of handlers provided by Kernel: "For Pack developers" and "Internal API".

### Pack Developer API

This is a handler that can be used directly in the Flow definition. A stable interface is guaranteed.

| Handler | Description | How to use in Flow |
|---------|------|----------------|
| `python_file_call` | Run Python file | `type: python_file_call` |
| `flow` | Call sub Flow | `type: flow` |
| `function` | Execute Capability function | `type: function` |
| `set` | Set value in context | `type: set` |
| `handler` | Directly call registered handler | `type: handler` |

### Internal API (not used by Pack developers)

A handler used for internal kernel operations. Pack developers do not need to call these directly.

| Category | Examples | Description |
|---------|-----|------|
| `kernel:*` | `kernel:ctx.get`, `kernel:ctx.set` | Context operations inside the Kernel |
| `flow.hooks.*` | `flow.hooks.pre_step`, `flow.hooks.post_step` | Flow lifecycle hook |
| `flow.construct.*` | `flow.construct.set`, `flow.construct.if` | Internal implementation of Flow syntax |
| `component_phase:*` | `component_phase:setup`, `component_phase:startup` | Component life cycle |

> **Note**: Internal APIs are subject to change without notice. Do not reference these directly from the Pack's Flow definition.

---

## Output key naming convention (details)

### Kernel internal key exclusion rules

When Flow execution results are returned as an HTTP response, keys starting with the following prefixes are automatically excluded as **Kernel internal keys**.

| Prefix | Description |
|---------------|------|
| `_flow_` | Flow control information |
| `_kernel_` | Kernel step metadata |
| `_step_out.` | Step output internal reference |
| `_current_step` | Current step number |
| `_total_steps` | Total number of steps |
| `_parent_flow` | Parent Flow information |
| `_principal_id` | Executor ID |
| `_flow_control` | Flow control signal |
| `_error` | Error information |
| `_flow_defaults` | Flow default value |

### If the Pack developer returns the `_` prefix key

`_` prefix keys that **do not match** the Kernel internal prefixes listed above (e.g. `_debug`, `_my_internal`) are not excluded from the response. However, a warning is logged.

```python
# この例では _debug は除外されず、レスポンスに含まれる（警告ログ付き）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_debug": {"raw_response": "..."},  # 警告ログが出るがレスポンスに残る
    }
```

### Recommendations

- We recommend not using the `_` prefix for Pack output keys
- If you want to include debug information, use regular key names like `debug` or `metadata`
- Key names that happen to match Kernel internal prefixes (e.g. `_flow_result`) should be specifically avoided as they will be unintentionally excluded.

```python
# ✅ 推奨
def run(input_data, context=None):
    return {
        "result": "ok",
        "debug_info": {"raw_response": "..."},
        "metadata": {"source": "my_pack", "version": "1.0"},
    }

# ⚠️ 非推奨（動作はするが警告ログが出る）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_debug": {"raw_response": "..."},
    }

# ❌ 避けるべき（Kernel 内部キーとして除外される）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_flow_result": "this will be silently removed",
        "_kernel_data": "this will also be removed",
    }
```


## Notes

- **InterfaceRegistry is an internal API.** Do not operate the IR directly from the Pack.
- **External communication must be done via Egress Proxy**. Use `context["http_request"]`.
- **lib can only be written to `/data`.** Writing to any other path will fail due to `--read-only`.
- Do not change **pack_identity.** apply will be rejected if `pack_identity` changes during update.
- **principal_id is forced to be overwritten by owner_pack in v1.** Even if you specify `principal_id` in the Flow definition or Modifier, the value of `owner_pack` will be used as the principal at runtime. If a discrepancy is detected, a warning is logged in the audit log.
- **About response size limit**: The response limit for Egress Proxy (`rumi_syscall`) and Capability Client (`rumi_capability`) is 4MB (can be changed in `RUMI_MAX_RESPONSE_BYTES`). However, the response limit for Capability Executor (server side subprocess execution) is 1MB.
- The default value size limit for **store.set is 1MB.** Can be changed with Grant's `grant_config.max_value_bytes`.
- **The minimum interval value of FlowScheduler is 10 seconds.** If you specify less than 10 seconds, it will be rounded up to the next 10 seconds.
- **The default number of simultaneous Flow executions is 10.** Can be changed using the `RUMI_MAX_CONCURRENT_FLOWS` environment variable.
- **Capability execution timeout limit is 120 seconds.** Even if you specify a value greater than 120 for `timeout_seconds` of `rumi_capability.call()`, it will be limited to 120 seconds. Default is 30 seconds.

### Hard links not supported

The use of hard links within Pack directories (`ecosystem/<pack_id>/`) is **unsupported**.

#### Reason

The Pack authorization/hash verification system uses the file path normalized with `Path.resolve()` as the cache key. Symbolic links are resolved into real paths by `resolve()`, so the source and destination are combined into the same cache entry. On the other hand, hard links are not unified in `resolve()` (each path entry is kept independent). Therefore, multiple paths pointing to the same inode are treated as separate cache entries, and changes to a file via one path may not be reflected in hash validation on the other.

```
hardlink_a.py ─┐
               ├─ 同一 inode → 内容は同一
hardlink_b.py ─┘

Path.resolve():
  hardlink_a.py → /abs/path/hardlink_a.py  ← キャッシュキー A
  hardlink_b.py → /abs/path/hardlink_b.py  ← キャッシュキー B（別エントリ）

symlink.py → target.py:
  symlink.py → /abs/path/target.py         ← target.py と同一キー ✓
```

#### Recommended Alternatives

- **Symbolic link**: Resolves to a real path in `resolve()`, making it consistent with hash validation. However, the reference destination of the symbolic link is limited to**within the pack_subdir boundary**. Symbolic links pointing outside the boundary are rejected at runtime.
- **File Copy**: The safest method. Each file has an independent hash and there are no verification issues.

---

## API Reference

### rumi_syscall (external communication)

This is a module for performing external HTTP communication from within a container. Used in `import rumi_syscall`.

| Function | Description |
|------|------|
| `http_request(method, url, headers=None, body=None, timeout_seconds=30.0)` | Generic HTTP request |
| `get(url, headers=None, timeout_seconds=30.0)` | GET shortcut |
| `post(url, body=None, headers=None, timeout_seconds=30.0)` | POST shortcut |
| `post_json(url, data, headers=None, timeout_seconds=30.0)` | JSON POST shortcut (Content-Type automatic setting) |
| `put(url, body=None, headers=None, timeout_seconds=30.0)` | PUT shortcut |
| `delete(url, headers=None, timeout_seconds=30.0)` | DELETE shortcut |
| `patch(url, body=None, headers=None, timeout_seconds=30.0)` | PATCH shortcut |
| `head(url, headers=None, timeout_seconds=30.0)` | HEAD shortcut |

The return value is a dict containing `success` (bool), `status_code` (int), `headers` (dict), `body` (str), `error` (str), `error_type` (str), `latency_ms` (float), `redirect_hops` (int), `bytes_read` (int), `final_url` (str), etc.

`request` is an alias for `http_request`. `rumi_syscall.request(...)` has the same behavior.

### rumi_capability (Capability call)

A module for calling Capability from within a container. Used in `import rumi_capability`.

| Function | Description |
|------|------|
| `call(permission_id, args=None, timeout_seconds=30.0, request_id=None)` | Execute Capability |

The return value is a dict containing `success` (bool), `output` (Any), `error` (str), `error_type` (str), `latency_ms` (float).

```python
import rumi_capability

result = rumi_capability.call("store.get", args={"store_id": "my_store", "key": "config"})
if result["success"]:
    data = result["output"]
```

---

## Tutorial: Create a simple Pack

Create a Pack that retrieves data from an external API, stores it in a Store, and returns it via an HTTP endpoint.

### 1. Directory structure

```
ecosystem/weather_pack/
└── backend/
    ├── ecosystem.json
    ├── routes.json
    ├── blocks/
    │   ├── fetch_weather.py
    │   └── get_cached_weather.py
    └── flows/
        ├── fetch_weather.flow.yaml
        └── get_weather.flow.yaml
```

### 2. ecosystem.json

```json
{
  "pack_id": "weather_pack",
  "pack_identity": "github:author/weather_pack",
  "version": "1.0.0",
  "description": "天気情報を取得・キャッシュする Pack"
}
```

### 3. Block: fetch_weather.py

```python
import rumi_syscall
import rumi_capability

def run(input_data, context=None):
    city = input_data.get("city", "Tokyo")

    # 外部 API からデータ取得（Network Grant 必要）
    result = rumi_syscall.get(
        f"https://api.example.com/weather?city={city}",
        timeout_seconds=10.0
    )
    if not result["success"]:
        return {"error": result["error"]}

    import json
    weather = json.loads(result["body"])

    # Store に保存（store.set Grant 必要）
    rumi_capability.call("store.set", args={
        "store_id": "weather_cache",
        "key": f"weather/{city}",
        "value": weather
    })

    return {"weather": weather}
```

### 4. Block: get_cached_weather.py

```python
import rumi_capability

def run(input_data, context=None):
    city = input_data.get("city", "Tokyo")

    result = rumi_capability.call("store.get", args={
        "store_id": "weather_cache",
        "key": f"weather/{city}"
    })

    if result["success"] and result["output"].get("success"):
        return {"weather": result["output"]["value"]}
    return {"error": "No cached data"}
```

### 5. Flow definition

```yaml
# flows/fetch_weather.flow.yaml
flow_id: weather_pack.fetch
schedule:
  interval: 300
phases:
  - main
steps:
  - id: fetch
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: weather_pack
    file: blocks/fetch_weather.py
    input:
      city: "Tokyo"
    output: result
```

```yaml
# flows/get_weather.flow.yaml
flow_id: weather_pack.get
phases:
  - main
steps:
  - id: get_cached
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: weather_pack
    file: blocks/get_cached_weather.py
    input:
      city: "${ctx.city}"
    output: result
```

### 6. routes.json

```json
{
  "routes": [
    {
      "method": "GET",
      "path": "/api/weather/{city}",
      "flow_id": "weather_pack.get",
      "description": "キャッシュ済みの天気情報を返す"
    }
  ]
}
```

### 7. Operational procedures

```bash
# Pack を承認
curl -X POST http://localhost:8765/api/packs/weather_pack/approve \
  -H "Authorization: Bearer YOUR_TOKEN"

# Network Grant を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "weather_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'

# Store を作成
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "weather_cache", "root_path": "user_data/stores/weather_cache"}'

# Capability Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "weather_pack", "permission_id": "store.set", "config": {"allowed_store_ids": ["weather_cache"]}}'

curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "weather_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["weather_cache"]}}'

# 天気情報を取得
curl http://localhost:8765/api/weather/Tokyo \
  -H "Authorization: Bearer YOUR_TOKEN"
```
# Defaultspack Function Contracts

Defaultspack capabilities are available as Rumi functions. Prefer calling aliases such as `defaults.ai.complete`, `defaultspack.chat.send`, or `defaultspack.ai.set_thinking_level` instead of depending on HTTP routes or defaultspack file paths. See [defaultspack-functions.md](defaultspack-functions.md) for examples, permissions, and AI tool wrapper guidance.
