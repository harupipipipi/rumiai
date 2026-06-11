<!-- docs-i18n-links:start -->
[EN](../../pack-development.md) | [JP](../ja/pack-development.md) | [KR](../ko/pack-development.md) | [CN](./pack-development.md)
<!-- docs-i18n-links:end -->

> **快速入门指南**：如果您想开始Pack开发，请参考【Pack开发快速入门指南】(./pack-development-guide.md)。
# Rumi AI OS — Pack 开发指南

Pack 开发人员指南。总体设计请参见[architecture.md](./architecture.md)，操作说明请参见[operations.md](./operations.md)。

---

## 目录

1.【开发流程】(#开发流程)
2.【最低配置】(#minimum-configuration)
3.[ecosystem.json](#生态系统json)
4. [方块](#块)
5.[Type hints/validation](#类型提示验证)
6. [流程定义](#流程定义)
7. [流程 → HTTP 响应映射](#flow--http-response-mapping)
8. [流量调节器](#流量调节剂)
9. [网络访问](#网络接入)
10. [context\["http\_request"\]详细规范](#contexthttp_request-详细规范)
11. [使用秘密（来自包）](#使用秘密（来自包）)
12. [使用能力](#使用能力)
13. [存储 API（通过功能）](#存储-api（通过功能）)
14.【Inter-Pack合作模式】(#跨包装合作模式)
15.[lib（install / update）](#libinstall--update)
16. [pip 依赖（requirements.lock）](#pip-依赖项（requirementslock）)
17.[permissions.json](#权限json)
18. [包括能力处理程序](#includes-capability-handler)
19.[vocab/converter (advanced)](#词汇转换器（高级）)
20. [组件（高级）](#组件（高级）)
21. [包特定端点 (routes.json)](#特定于包的端点-routesjson)
22.【HTTP状态码控制】(#http状态码控制)
23. [错误处理最佳实践](#错误处理最佳实践)
24. [流量调节器推荐模式](#流量调节剂推荐模式)
25.【Handler API分类】(#处理程序api分类)
26.【输出键命名约定（详情）】(#输出键命名约定（详情）)
27. [注释](#注释)
28. [API 参考](#api参考)
29. [教程：创建一个简单的包](#教程：创建一个简单的包)

---

## 开发流程

### 步骤0：使用模板生成模板

```bash
python -m core_runtime.pack_scaffold my-pack --template minimal --output-dir ecosystem/
```

模板类型：
- `minimal`：最小配置（ecosystem.json + run.py）
- `capability`：带有能力处理程序
- `flow`：具有流程定义
- `full`：全部包含

1. **创建包** — 将文件放入`ecosystem/<pack_id>/backend/`中
2. **编写ecosystem.json** — 打包元数据（需要`pack_id`、`pack_identity`）
3. **写入块/** — `python_file_call`中调用的代码
4. **写入流程** — 放置在 Pack and connect 块中的 `user_data/shared/flows/` 或 `flows/` 中
5. **获得批准** — 用户批准该包
6. **执行**——批准后，执行Flow时调用块

---

## 最低配置

```
ecosystem/my_pack/
└── backend/
    ├── ecosystem.json
    └── blocks/
        └── hello.py
```

> **关于路径**：`ecosystem/<pack_id>/`是推荐路径。 `ecosystem/packs/<pack_id>/` 也支持作为兼容路径，但如果两者中存在相同的 `pack_id`，则 `ecosystem/<pack_id>/` 优先。

---

## 生态系统.json

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

### 连接性（包间依赖声明）

您可以通过将 `connectivity` 字段添加到 `ecosystem.json` 来声明包之间的依赖关系。

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

连接性`requires` / `provides` 用于在启动时自动解析包加载顺序 (load_order)。首先加载第 `provides` `requires` 中指定的服务的包。

如果存在手动规范（`ecosystem.json`的`load_order`字段），则优先。仅在没有手动指定的情况下才应用自动解析。

目前，连接的唯一运行时影响是自动加载顺序解析。未来可能会扩大。

#### 连接模式示例

| provides | Meaning | Typical Pack |
|----------|------|--------------|
| `ai.client` | AI API Client | OpenAI / Anthropic Client |
| `tool.registry` | Tool registration | Tool manager |
| `memory.store` | Memory Store | Memory Management |
| `ui.chat` | Chat UI | Frontend |

提供/要求值是点分隔的自由字符串。操作系统不会解释该值的含义，仅将其用于自动解析load_order。请匹配包开发者之间的名称。

---

## 块

由`python_file_call`调用的Python文件。

### 基本形式

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

`run` 函数还允许仅使用 `input_data` 的单参数版本。

### 返回值

请返回 JSON 兼容的字典。返回的值按原样存储在 Flow 的 `output` 字段中指定的上下文键中。内核内部的包装器（例如`_kernel_step_status`）会自动删除，块返回的值直接进入`ctx[output_key]`。

### 输出键命名约定

以下规则适用于存储在 Flow 步骤的 `output` 中的值的键名称。

以 `_` 前缀开头的键被保留为内核内部键。如果 `python_file_call` 的 `run()` 返回的字典包含带有 `_` 前缀的键（例如 `_kernel_step_status`、`_debug`），则它们在存储在 Flow 的 `output` 上下文中时将被自动排除。

不要在 Pack 块返回的输出键上使用 `_` 前缀。这可能会导致您无意中被排除在外。

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

## 类型提示/验证

### run() 函数签名

`python_file_call` 调用的`run()` 函数接受以下三种模式之一。执行引擎自动检测`inspect.signature`中的参数数量。

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

### input_data 的类型安全

`input_data` 是流定义的`input` 字段的 JSON 序列化/反序列化值。因此，包含的类型仅限于以下 JSON 派生类型：

| JSON type | Python type |
|---------|----------|
| object | `dict` |
| array | `list` |
| string | `str` |
| number (integer) | `int` |
| number (decimal) | `float` |
| boolean | `bool` |
| null | `None` |

`input_data`本身通常是`dict`，但如果您直接在流定义中指定标量值或列表，它将属于该类型。

### 上下文类型

`context` 是`dict[str, Any]`。主要按键是：

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

### 返回类型

`run()`的返回值必须是JSON可序列化值（`dict`、`list`、`str`、`int`、`float`、`bool`、`None`）。如果返回`None`，则流输出将被视为`null`。如果返回值为`dict`，则其内容存储在流的`output`变量中。

### 验证最佳实践

`input_data` 的内容源自外部来源（流程定义和用户输入），因此请务必对其进行验证。

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

**推荐：**

- 不抛出异常，而是返回`{"error": "..."}`并正常退出。
- 检查函数开头的所有必填字段
- 严格按照`isinstance()`检查类型
- 设置数字范围和列表长度的限制

---

## 流程定义

### 放置路径

| Path | Purpose |
|------|------|
| `user_data/shared/flows/` | Share Flow. Suitable for wiring across multiple packs |
| `ecosystem/<pack_id>/backend/flows/` | Pack-specific Flow |

### 示例

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

### 步骤怎么写

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

#### 处理程序

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

`handler`类型直接调用`input.handler`（`kernel:*`）中指定的内核处理程序或InterfaceRegistry注册的处理程序。 `input.args` 作为参数传递给处理程序。

#### 设置

```yaml
- id: set_default
  phase: prepare
  priority: 5
  type: set
  input:
    key: "model"
    value: "gpt-4"
```

> **注意**：`set`类型由InterfaceRegistry中注册的`flow.construct.set`处理程序处理。 Flow 加载器将 `set` 解释为标准步骤类型，但执行是通过构造进行的。 `set` 如果构造未注册，则跳过该步骤。

#### 流（子流调用）

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

`flow`类型将另一个Flow称为子Flow。递归调用（循环引用）会被自动检测并导致错误。子 Flow 的上下文是从父 Flow 深度复制的，并添加了 `args` 中指定的值。

#### 函数（能力函数调用）

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

`function`类型执行通过`capability_executor`在FunctionRegistry中注册的函数。在 `function` 字段中指定 `permission_id`（例如，`store.get`）。执行需要相应的能力授予。

| Field | Required | Description |
|-----------|------|------|
| `type` | ✅ | `function` |
| `function` | ✅ | permission_id of the function to be executed (e.g. `store.get`, `docker.run`) |
| `input` | Any | Argument to the function (variable expansion possible) |
| `output` | Optional | Output destination context key |
| `vocab_normalize` | Optional | For `true`, vocab normalize the value of `function` before solving |

### 变量扩展

您可以使用 `${ctx.key}` 引用上下文中的值。嵌套引用 (`${ctx.user.id}`) 也是可能的。如果引用不存在，则为 `null`。

### 安排执行

通过将 `schedule` 字段添加到流程中可以定期执行。

#### cron 表达式（5 个字段：分钟、小时、日、月、星期几）

```yaml
flow_id: daily_cleanup
schedule:
  cron: "0 0 * * *"

phases:
  - main
steps:
  # ...
```

#### 间隔（指定秒数，最少 10 秒）

```yaml
flow_id: health_check
schedule:
  interval: 30

phases:
  - main
steps:
  # ...
```

cron 表达式支持 `*`、`*/N`、数字、逗号分隔、范围 (`N-M`) 和范围+步长 (`N-M/S`)。调度程序以每 10 秒的时钟周期为单位进行评估，因此 cron 的精度以分钟为单位。自动防止同一流程的重复执行。

### 流量控制协议

您可以通过在块的返回值中返回`__flow_control`键来控制流程的执行。

#### 流量中断

```python
def run(input_data, context=None):
    if not input_data.get("valid"):
        return {"__flow_control": "abort", "reason": "Invalid input"}
    return {"result": "ok"}
```

返回`{"__flow_control": "abort", "reason": "..."}`会中断流程，而不执行任何进一步的步骤。暂停的原因记录在诊断中。

> 目前，`__flow_control`仅支持`"abort"`。其他值将被忽略。

---

## 流程 → HTTP 响应映射

当Pack的`routes.json`中定义的端点接收到HTTP请求时，Pack API服务器（`pack_api_server.py`）执行相应的Flow，将结果转换为HTTP响应，然后返回。

### 响应转换的工作原理

在当前实现中，Flow 执行结果（`outputs`）**始终以 JSON 格式返回**。响应是通过 `APIResponse` 数据类生成的。

```python
@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
```

如果流程成功运行：

```json
{
  "success": true,
  "data": { "...Flow outputs がここに入る..." },
  "error": null
}
```

如果流程执行失败：

```json
{
  "success": false,
  "data": null,
  "error": "エラーメッセージ"
}
```

### 状态码

Pack API 服务器的`_send_response` 使用以下 HTTP 状态代码。

| Status | Status Code |
|------|-----------------|
| Flow execution successful | `200 OK` |
| Authentication failure | `401 Unauthorized` |
| Invalid input | `400 Bad Request` |
| Route not found | `404 Not Found` |
| Internal error | `500 Internal Server Error` |

### 标题

以下标头会自动添加到响应中。

| Header | Value | Condition |
|---------|-----|------|
| `Content-Type` | `application/json; charset=utf-8` | Always granted |
| `Access-Control-Allow-Origin` | Requested by Origin | Matches CORS allow list |
| `Vary` | `Origin` | When adding CORS header |

### 使用特殊键控制

目前 **不支持** 使用特殊键（例如 `_status_code`、`_headers`、`_body`）直接控制 HTTP 响应。流输出始终存储在 `APIResponse` 的 `data` 字段中，并以 `application/json` 格式返回。

如果您需要自定义状态代码或标头控制，请参阅[HTTP 状态代码控制](#http状态码控制)。

---

## 流量调节器

这是一种稍后将函数插入现有流程的机制。

### 放置路径

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/`

### 示例

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

### 可用的操作

| action | description |
|--------|------|
| `inject_before` | Insert before specified step |
| `inject_after` | Insert after specified step |
| `append` | Add to end of phase |
| `replace` | Replace specified step |
| `remove` | Delete specified step |

> **阶段约束**：修改器的`phase`必须包含在目标流的`phases`列表中。如果指定不存在的阶段，则将跳过修改器。

> **应用顺序**：修饰符按阶段→优先级→modifier_id排序并确定性应用。如果同一注入点有多个修饰符（`inject_before` / `inject_after` 到同一个`target_step_id`），它们会按照优先级→step.id→modifier_id 的顺序一次性插入，以防止由于索引移位而导致的不确定性。 `replace` / `remove` 在注入/附加之前应用。

### 通配符 target_flow_id

您可以在`target_flow_id`中使用通配符模式将修饰符同时应用于多个流。

| Pattern | Meaning |
|----------|------|
| `*` | Applies to all Flows |
| `my_pack.*` | Applies to all Flows starting with `my_pack.` |

Python的`fnmatch`用于匹配。

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

### 需要条件

```yaml
requires:
  interfaces:
    - "ai.client"
  capabilities:
    - "tool_support"
```

如果不满足条件，则将跳过修饰符。

---

## 网络访问

### 概述

包在 Docker `--network=none` 中是隔离的，不能直接与外部通信。外部通信需要网络授权，所有请求都通过出口代理（UDS 套接字）。

### 块内的 HTTP 请求

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

> **超时限制**：`timeout_seconds` 的最大值为 120 秒。任何大于 120 的值都将被截断为 120 秒。此限制适用于`rumi_syscall` 和`rumi_capability`。

### 预先检查访问可用性

```python
def run(input_data, context=None):
    check = context.get("network_check")
    result = check("api.openai.com", 443)

    if not result["allowed"]:
        return {"error": result["reason"]}

    # 通信可能
```

### 如何获得补助金

由用户或运营商通过 API 授予。有关详细信息，请参阅[operations.md](./operations.md)中的“网络权限管理”。

---

## context["http_request"] 详细规范

`python_file_call`的`run(input_data, context)`中传递的`context["http_request"]`是Pack代码进行外部HTTP通信的唯一方式。

### 函数签名

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

### 参数

| Parameters | Type | Default | Description |
|------------|-----|-----------|------|
| `method` | `str` | (Required) | HTTP method. `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD` |
| `url` | `str` | (required) | Complete URL to request |
| `headers` | `dict[str, str] \| None` | `None` | HTTP request headers |
| `body` | `str \| None` | `None` | Request body (string). When sending JSON, pass the `json.dumps()` string |
| `timeout_seconds` | `float` | `30.0` | Timeout seconds. Limited to maximum `120.0` seconds |

### 返回值

关于成功：

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

失败时：

```python
{
    "success": False,
    "error": "エラーメッセージ",     # str: エラー内容
    "error_type": "timeout",       # str: エラー種別
}
```

### error_type 列表

| error_type | description |
|------------|------|
| `socket_not_found` | Egress Proxy socket not found |
| `permission_denied` | No permission to access socket |
| `connection_refused` | Connection to Egress Proxy was refused |
| `timeout` | Request timed out |
| `syscall_error` | Protocol level error |
| `json_decode_error` | JSON parsing of response failed |
| `grant_denied` | Access denied due to Network Grant |

### 通过 UDS 出口代理进行通信

来自 Pack 代码的所有外部 HTTP 通信都会通过 **UDS（Unix 域套接字）出口代理**。 Pack 代码无法进行直接网络通信。

通讯流程：

```
Pack コード (run関数)
  → context["http_request"]()
    → UDS ソケット (/run/rumi/egress/packs/{pack_id}.sock)
      → Egress Proxy (Kernel 側)
        → Network Grant Manager でアクセス許可を検証
          → 許可されていれば外部 HTTP リクエストを実行
          → 拒否されていれば grant_denied エラーを返却
```

> 可以使用 `RUMI_EGRESS_SOCK_DIR` 环境变量更改套接字路径。默认为`/run/rumi/egress/packs`。

### 容器模式和主机模式的区别

| Item | Container mode (strict) | Host mode (permissive) |
|------|--------------------------|---------------------------|
| Network | `--network=none` (Complete isolation) | Use host network |
| Communication path | Only via UDS socket | Via UDS socket (via helper function) |
| Socket path | `/run/rumi/egress/packs/{pack_id}.sock` (Inside container mount) | `{RUMI_EGRESS_SOCK_DIR}/{pack_id}.sock` |
| Grant Validated | Egress Proxy Validated | Egress Proxy Validated |
| Security | Docker Quarantine + UDS Restrictions | Run with warnings (not recommended for production) |

在容器模式（`RUMI_SECURITY_MODE=strict`）下，Docker容器以`--network=none`启动，因此除了UDS套接字之外没有其他通信方式。主机模式（`RUMI_SECURITY_MODE=permissive`）无需 Docker 即可运行，但`context["http_request"]`也经过 Egress Proxy，因此 Network Grant 的控制是有效的。

### 使用示例

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

## 使用秘密（来自 Pack）

包使用 `secrets.get` 能力来获取机密（例如 API 密钥）。在运营商注册秘密并授予资助后，它就变得可用。

### 使用示例

```python
import rumi_capability

result = rumi_capability.call("secrets.get", args={"key": "OPENAI_API_KEY"})
if result["success"]:
    api_key = result["output"]["value"]
else:
    # "Access denied or secret not found"
    error = result["output"]["error"]
```

### 访问控制

`secrets.get` 授权必须明确指定可在 `grant_config.allowed_keys` 中访问的密钥。如果`allowed_keys`为空或未指定，则拒绝访问所有密钥（失败关闭）。

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

### 重要限制

- `get`只能通过能力获得。不存在可直接重新显示秘密值的 API
- 速率限制应用于`secrets.get`（默认60次/分钟/包，可以通过环境变量`RUMI_SECRET_GET_RATE_LIMIT`更改，滑动窗口方法）
- 值永远不会包含在日志、审核或异常消息中
- 无法从错误消息中确定密钥是否存在（统一为“访问被拒绝或密钥未找到”）

---

## 使用能力

对于要使用功能处理程序的 Pack（例如读取文件系统、运行外部工具等），必须向 Pack 授予适当的权限。

### 信托与赠与之间的关系

能力需要两个级别的批准。

1. **信任注册**（handler授权）：将handler的代码（sha256）注册为可信
2. **Grant**（权限授予）：授予已批准的处理程序对 Pack 的权限。

```
handler.py が信頼される（Trust 登録）
    ↓
Pack に permission が付与される（Grant 付与）
    ↓
Pack が capability を使用可能
```

即使信托已注册，未经拨款也无法使用。相反，即使有授权，未注册信任的处理程序也无法执行。

### 如何调用能力

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})
if result["success"]:
    content = result["output"]
else:
    error = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
```

### 内置功能处理程序

以下功能处理程序包含在核心运行时中，无需信任注册即可使用（需要单独授予）。

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

### 格兰特 格兰特

补助金由使用 API 的用户或运营商授予。有关详细信息，请参阅第 [operations.md](./operations.md) 中的“能力授予管理”。

```bash
# 例: store.get の Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["my_store"]}}'
```

### 授予配置（grant_config）

补助金可以在`config`中设定限制。设置因权限而异。

| permission_id | grant_config key | description |
|---------------|-------------------|------|
| `secrets.get` | `allowed_keys` | List of accessible key names (required, completely denied if empty) |
| `store.get/set/delete/list` | `allowed_store_ids` | List of accessible store_ids (required, completely rejected if empty) |
| `store.set` | `max_value_bytes` | Maximum write size (bytes, default 1MB) |

`allowed_keys` / `allowed_store_ids` 是失败关闭的。如果列表为空或未指定，则所有访问都将被拒绝。

### 错误处理

如果功能调用失败，则返回包含 `success: False` 的字典。

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

## 存储 API（通过功能）

### 概述

Store 是可以在 Pack 之间共享的键值存储。存储操作是通过 Capability 执行的。当操作员向包授予能力授权时，将启用访问权限。

### 可用的permission_id

| permission_id | description | args |
|---------------|------|------|
| `store.get` | Read value from Store | `store_id`, `key` |
| `store.set` | Write value to Store | `store_id`, `key`, `value` |
| `store.delete` | Remove value from Store | `store_id`, `key` |
| `store.list` | Get list of keys in Store | `store_id`, `prefix` (optional) |

### 使用示例

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

> `store.list` 的`output` 包含`success`（布尔值）和`keys`（键名数组）。

```python
# 値の削除
result = rumi_capability.call("store.delete", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
```

### 授予设置

`store.*` 中的补助金可以具有 `grant_config` 中规定的限制：

| grant_config key | Description | Default |
|-------------------|------|-----------|
| `allowed_store_ids` | List of store_ids to allow access | `[]` (If the list is empty, access to all Stores is denied. Store_id must be explicitly specified to access) |
| `max_value_bytes` | `store.set` maximum size (bytes) | 1MB (1048576) |

`allowed_store_ids` 是失败关闭的。如果您在创建授权时未指定`allowed_store_ids`或指定空列表`[]`，则该授权将拒绝访问所有商店。对于要访问 Store 的 Pack，操作员必须显式地将 store_id 添加到列表中。

### 创建商店

商店创建是使用操作 API 完成的：

```bash
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "my_store", "root_path": "user_data/stores/my_store"}'
```

> **store_id 约束**：`store_id` 必须匹配`^[a-zA-Z0-9_-]{1,64}$`。

### 内置功能处理程序列表

以下功能处理程序包含在核心运行时中，无需信任注册即可使用（需要单独授予）。

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

## 跨包合作模式

### 使用共享流进行接线

来自多个包的块可以使用放置在`user_data/shared/flows/`中的流来连接。包不需要互相了解。

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

### 通过 Store 传输数据

使用 Stores 在不同 Flow 中工作的 Pack 之间共享数据。

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

## lib（安装/更新）

### 概述

这是一个仅在 Pack 初始化或更新时执行一次的脚本。它通常不会被执行。

### 文件结构

```
ecosystem/<pack_id>/backend/lib/
├── install.py    # 初回導入時に実行
└── update.py     # ハッシュ変更時に実行（なければ install.py が実行される）
```

### install.py 示例

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

### 上下文提供的信息

| Key | Description |
|------|------|
| `pack_id` | Pack ID |
| `lib_type` | `"install"` or `"update"` |
| `ts` | Timestamp |
| `lib_dir` | lib directory path (inside container: `/lib`) |
| `data_dir` | Writable directory (in container: `/data`, host: `user_data/packs/{pack_id}/`) |

### 安全限制

在严格模式下，它在 Docker 容器内隔离运行。 `--network=none`、`--read-only`。只能写入 `/data` (= `user_data/packs/{pack_id}/`)。

---

## pip 依赖项 (requirements.lock)

### 概述

如果您的包依赖于 PyPI 包，请包含 `requirements.lock`。

### 放置路径

按以下顺序搜索：

1.`<pack_subdir>/requirements.lock`
2. `<pack_subdir>/backend/requirements.lock`（兼容）

### 格式

仅允许使用 `NAME==VERSION` 行。允许注释行和空行。

```
requests==2.31.0
flask==3.0.0
```

禁止使用以下内容：`-e`、`git+`、`http://`、`https://`、`file:`、`../`、`/`、`--`可选行、`@`直接引用。

### 包代码中的用法

批准并安装后，只需照常运行`import`即可。

```python
import requests  # pip で導入された依存

def run(input_data, context=None):
    resp = requests.get("https://api.example.com/data")
    return {"data": resp.json()}
```

在执行容器中，站点包作为 `/pip-packages:ro` 挂载并添加到 `PYTHONPATH` 中。

### 如何获得批准

用户或运营商通过API批准。有关详细信息，请参阅第 [operations.md](./operations.md) 中的“pip 依赖库管理”。

---

## 权限.json

声明 Pack 所需权限的文件。

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

Permissions.json 是声明性的，不会在运行时强制执行。实际的访问控制是通过能力授予和网络授予来完成的。此文件仅供用户参考（此包需要什么权限）。

---

## 包括能力处理程序

当 Pack 提供功能处理程序时，它遵循以下约定：

### 安置

```
ecosystem/<pack_id>/
└── backend/
    └── share/
        └── capability_handlers/
            └── <slug>/
                ├── handler.json
                └── handler.py
```

将其放在包装的 `pack_subdir`（通常为 `ecosystem/<pack_id>/backend/`）下的 `share/capability_handlers/<slug>/` 中。

### 处理程序.json

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

通过扫描检测候选者，经用户批准，并复制到`user_data/capabilities/handlers/<slug>/`。 Approve仅注册Trust（sha256白名单），需要单独授予Grant。

> 以上是老方法（兼容）。新包推荐使用以下功能/方法：

### 函数/方法（推荐）

如果您的 Pack 提供 Capability 函数，请将它们放在 `functions/` 目录中。

#### 安置

```
ecosystem/<pack_id>/
└── backend/
    └── functions/
        └── <function_id>/
            ├── manifest.json
            └── main.py
```

#### 清单.json

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

> **注意**：manifest.json 中不存在 `permission_id` 字段。使用 `requires` 数组指定权限。

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

如果 `calling_convention` 为 `block`（默认），则入口点为 `execute(context, args)`。 `context`包含诸如`grant_config`之类的执行信息，并且`args`传递在流程步骤的`input`中指定的值。

---

## 词汇/转换器（高级）

> 正常Pack开发中无需使用。兼容性吸收的高级功能。

### 词汇.txt

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

写在同一行上的单词被视为同义词。

### 转换器

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

---

## 组件（高级）

组件是具有`components/{component_id}/manifest.json`的单元，用于生命周期管理（设置等）。 `python_file_call` 不会特殊对待组件，因此请在`file` 字段中指定相对路径。

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

### setup.py 的基本模式

Component 的初始化过程在`components/{component_id}/setup.py`中描述。

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

设置在启动时的`kernel:component.load`步骤中执行。

---

## 包特定端点 (routes.json)

### 概述

包可以包含 `routes.json` 以在 HTTP API 服务器上注册自己的端点。接收到的请求执行指定的Flow并将结果作为响应返回。

### 放置路径

`ecosystem/<pack_id>/backend/routes.json`

### routes.json 格式

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

### 路径参数

路径参数可以使用`{param}`符号来定义。路径参数值自动包含在 Flow 的`inputs`中。

示例：如果您请求 `/api/orgs/{org_id}/tasks/{task_id}`，则 `inputs.org_id` 和 `inputs.task_id` 将具有各自的值。

### 获取查询参数

GET 请求的查询参数也包含在`inputs`中。

### 获取原始正文/标头

Flow 的`inputs`还包括以下特殊键：

| Key | Description |
|------|------|
| `_raw_body` | base64 encoded value of request body |
| `_headers` | dict of request headers |
| `_method` | HTTP methods (GET, POST, etc.) |
| `_path` | Request path |

### 重新加载路线

```bash
curl -X POST http://localhost:8765/api/routes/reload \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 检查已注册的路线

```bash
curl http://localhost:8765/api/routes \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## HTTP状态码控制

### 当前规格

当前 Pack API 服务器实现**不允许 Pack 直接控制从 Pack 的 `routes.json` 端点返回的 HTTP 状态代码。

即使您在流的输出中包含特殊键（例如 `_status_code`），它也只会包含在响应的 `data` 字段中，而不会反映在 HTTP 状态代码中。

### 状态码判断逻辑

Pack API Server 使用以下逻辑确定状态代码。

| Judgment order | Status | Status code |
|--------|------|-----------------|
| 1 | Authentication failure | `401` |
| 2 | Input validation failure | `400` |
| 3 | Route not found | `404` |
| 4 | Flow execution successful | `200` (fixed) |
| 5 | Error dict returned when running Flow | `200` (data contains error but HTTP is 200) |
| 6 | Exception occurs during Flow execution | `500` |

这意味着即使流程成功完成并返回 `{"error": "not found"}`，HTTP 状态代码也将为 `200 OK`。

### 推荐图案

在当前限制下，使用响应正文中的 `success` 和 `error` 字段将错误传达给客户端。

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

在客户端，成功/失败取决于`data.error`的存在与否。

### 计划未来的支持

在未来的版本中，我们正在考虑添加识别 Flow 输出中的特殊键（`_status_code`、`_headers` 等）的功能，并将其反映在 HTTP 响应中。

---

## 错误处理最佳实践

### 如果 python_file_call 的 run() 发生异常

`run()` 当函数内发生未捕获的异常时，执行引擎将执行以下操作：

**容器模式**：Docker 进程以非零退出代码退出，并且 stderr 的内容被记录为错误消息。 `ExecutionResult`的`success`变成`False`，`error_type`变成`"container_execution_error"`。**主机模式（宽容）**：异常从`ThreadPoolExecutor`中的`Future`传播，类似地，`ExecutionResult`中的`success`变成`False`。

无论哪种情况，内核的处理程序（`_h_python_file_call`）都会返回`_kernel_step_status: "failed"`。

### 推荐：用 try- except 包装并返回错误字典

如果泄漏异常，则仅记录堆栈跟踪，并且不会将任何有用信息传递给调用流程。请务必将其包装在 try-except 中并返回结构化错误信息。

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

### Flow 步骤失败时的行为

流程中的步骤失败时的行为由流程定义中的`defaults`和每步骤`on_error`设置决定。

| Settings | Behavior |
|------|------|
| `defaults.fail_soft: true` (default) | Record step failure and proceed to next step |
| `defaults.fail_soft: false` | Interrupt the entire Flow when a step fails |
| `on_error.action: "abort"` | Abort Flow if this step fails |
| `on_error.action: "continue"` | Continue even if this step fails |
| `on_error.action: "disable_target"` | Disable target and proceed |

如果流程级别错误处理程序在 InterfaceRegistry 中注册为 `flow.error_handler`，则当步骤异常发生时，将调用该处理程序。错误处理程序可以通过返回 `"abort"`（中止）、`"retry"`（重试）或其他内容（继续）来控制行为。

### 在capability.call()失败的情况下如何处理返回值

如果您通过 `rumi_capability` 模块调用 Capability，则失败时将返回包含 `success: False` 的字典。

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

能力调用失败的可能原因包括：

| error_type | description |
|------------|------|
| `approval_denied` | Not authorized for use of Capability |
| `grant_denied` | Capability Grant not granted |
| `trust_denied` | Trust Store verification failed |
| `handler_not_found` | The specified Capability Handler does not exist |
| `execution_error` | An error occurred while running Handler |
| `timeout` | Execution timed out |
| `socket_not_found` | Capability socket not found |

我们建议您使用返回值的 `success` 字段检查这些错误，而不是使用 try- except。

---

---

## Flow Modifier 推荐模式

流量修改器是一个强大的功能，但如果您尝试从一开始就使用所有操作，它可能会很复杂。我们建议从以下两种模式开始。

### 模式 1：追加（添加到阶段末尾）

这是最安全且最容易理解的模式。在不改变现有Flow的情况下将处理添加到最后。

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

何时使用：添加日志记录、审核、通知和后处理

### 模式2：替换（步骤替换）

这是一种替代现有步骤实施的模式。例如，在将 AI 客户端从 OpenAI 切换到 Anthropic 时使用此选项。

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

何时使用：更换实现、切换提供者

### 何时使用inject_before/inject_after

当您想要在特定步骤之前和之后插入处理时，请使用inject_before/inject_after。然而，由于它取决于目标步骤的 id，因此很容易受到流程结构变化的影响。仅在以下情况下考虑使用它：

- 如果特定步骤的输入数据需要预先转换（inject_before）
- 如果您需要对特定步骤的输出数据进行后处理（inject_after）
- 如果执行时间对于追加来说太慢

### 删除是最后的手段

删除会删除现有步骤，并且可以显着改变流程的行为。通过替换提供替代实现通常更安全。

---

## Handler API 分类

内核提供了两种类型的处理程序：“针对 Pack 开发人员”和“内部 API”。

### 包开发者 API

这是一个可以直接在流定义中使用的处理程序。保证了稳定的接口。

| Handler | Description | How to use in Flow |
|---------|------|----------------|
| `python_file_call` | Run Python file | `type: python_file_call` |
| `flow` | Call sub Flow | `type: flow` |
| `function` | Execute Capability function | `type: function` |
| `set` | Set value in context | `type: set` |
| `handler` | Directly call registered handler | `type: handler` |

### 内部 API（Pack 开发人员不使用）

用于内部内核操作的处理程序。包开发人员不需要直接调用这些。

| Category | Examples | Description |
|---------|-----|------|
| `kernel:*` | `kernel:ctx.get`, `kernel:ctx.set` | Context operations inside the Kernel |
| `flow.hooks.*` | `flow.hooks.pre_step`, `flow.hooks.post_step` | Flow lifecycle hook |
| `flow.construct.*` | `flow.construct.set`, `flow.construct.if` | Internal implementation of Flow syntax |
| `component_phase:*` | `component_phase:setup`, `component_phase:startup` | Component life cycle |

> **注意**：内部 API 如有更改，恕不另行通知。不要直接从 Pack 的 Flow 定义中引用这些内容。

---

## 输出键命名约定（详细）

### 内核内部键排除规则

当流程执行结果作为 HTTP 响应返回时，以以下前缀开头的键将自动排除为 **内核内部键**。

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

### 如果包开发者返回 `_` 前缀键

**不匹配**上面列出的内核内部前缀的`_`前缀键（例如`_debug`、`_my_internal`）不会从响应中排除。但是，会记录一条警告。

```python
# この例では _debug は除外されず、レスポンスに含まれる（警告ログ付き）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_debug": {"raw_response": "..."},  # 警告ログが出るがレスポンスに残る
    }
```

### 建议

- 我们建议不要对 Pack 输出键使用 `_` 前缀
- 如果您想包含调试信息，请使用常规键名称，例如 `debug` 或 `metadata`
- 应特别避免与内核内部前缀（例如 `_flow_result`）相匹配的键名，因为它们会被无意中排除。

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


## 注释

- **InterfaceRegistry 是一个内部 API。** 不要直接从 Pack 操作 IR。
- **外部通信必须通过出口代理完成**。使用`context["http_request"]`。
- **lib 只能写入`/data`。** 写入任何其他路径将因`--read-only`而失败。
- 请勿更改 **pack_identity。** 如果 `pack_identity` 在更新过程中发生更改，应用将被拒绝。
- **principal_id 在 v1 中被强制被 Owner_pack 覆盖。** 即使您在 Flow 定义或修饰符中指定了 `principal_id`，`owner_pack` 的值也将在运行时用作主体。如果检测到差异，则会在审核日志中记录一条警告。
- **关于响应大小限制**：出口代理 (`rumi_syscall`) 和功能客户端 (`rumi_capability`) 的响应限制为 4MB（可在 `RUMI_MAX_RESPONSE_BYTES` 中更改）。但是，Capability Executor（服务器端子进程执行）的响应限制为 1MB。
- **store.set 的默认值大小限制为 1MB。** 可以使用 Grant 的`grant_config.max_value_bytes` 进行更改。
- **FlowScheduler 的最小间隔值为 10 秒。** 如果指定小于 10 秒，则会向上舍入到接下来的 10 秒。
- **同时执行 Flow 的默认数量为 10。** 可以使用 `RUMI_MAX_CONCURRENT_FLOWS` 环境变量进行更改。
- **功能执行超时限制为 120 秒。** 即使您为 `rumi_capability.call()` 的 `timeout_seconds` 指定大于 120 的值，它也会被限制为 120 秒。默认值为 30 秒。

### 不支持硬链接

**不支持**在 Pack 目录 (`ecosystem/<pack_id>/`) 中使用硬链接。

#### 原因

Pack 授权/哈希验证系统使用以 `Path.resolve()` 规范化的文件路径作为缓存密钥。符号链接通过`resolve()`解析为真实路径，因此源和目标被组合到同一个缓存条目中。另一方面，硬链接在`resolve()`中并不统一（每个路径条目保持独立）。因此，指向同一 inode 的多个路径被视为单独的缓存条目，并且通过一个路径对文件的更改可能不会反映在另一路径上的哈希验证中。

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

#### 推荐的替代方案

- **符号链接**：解析为`resolve()`中的真实路径，使其与哈希验证一致。但是，符号链接的引用目标仅限于**pack_subdir 边界内**。指向边界之外的符号链接在运行时会被拒绝。
- **文件复制**：最安全的方法。每个文件都有独立的哈希值，不存在验证问题。

---

## API 参考

### rumi_syscall（外部通信）

这是一个用于从容器内执行外部 HTTP 通信的模块。用于`import rumi_syscall`。

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

返回值是一个包含 `success` (bool)、`status_code` (int)、`headers` (dict)、`body` (str)、`error` (str)、`error_type` (str)、`latency_ms` (float)、`redirect_hops` (int)、`bytes_read` (int)、`final_url` (str) 等的字典。

`request` 是 `http_request` 的别名。 `rumi_syscall.request(...)` 具有相同的行为。

### rumi_capability（功能调用）

用于从容器内调用功能的模块。用于`import rumi_capability`。

| Function | Description |
|------|------|
| `call(permission_id, args=None, timeout_seconds=30.0, request_id=None)` | Execute Capability |

返回值是一个包含 `success` (bool)、`output` (Any)、`error` (str)、`error_type` (str)、`latency_ms` (float) 的字典。

```python
import rumi_capability

result = rumi_capability.call("store.get", args={"store_id": "my_store", "key": "config"})
if result["success"]:
    data = result["output"]
```

---

## 教程：创建一个简单的包

创建一个 Pack，从外部 API 检索数据，将其存储在 Store 中，并通过 HTTP 端点返回数据。

### 1.目录结构

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

### 2.生态系统.json

```json
{
  "pack_id": "weather_pack",
  "pack_identity": "github:author/weather_pack",
  "version": "1.0.0",
  "description": "天気情報を取得・キャッシュする Pack"
}
```

### 3. 区块：fetch_weather.py

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

### 4. 块：get_cached_weather.py

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

### 5. 流程定义

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

### 6.routes.json

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

### 7.操作流程

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
# Defaultspack 函数合约

Defaultspack 功能可作为 Rumi 函数使用。优先调用 `defaults.ai.complete`、`defaultspack.chat.send` 或 `defaultspack.ai.set_thinking_level` 等别名，而不是依赖 HTTP 路由或默认包文件路径。有关示例、权限和 AI 工具包装指南，请参阅[defaultspack-functions.md](defaultspack-functions.md)。
