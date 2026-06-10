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
3.§鲁米§0§
4. [块](#块)
5.§鲁米§0§
6. [流程定义](#流程定义)
7. [流程 → HTTP 响应映射](#flow--http-response-mapping)
8. [流量调节剂](#流量调节剂)
9. [网络访问](#网络接入)
10. [context\["http\_request"\]详细规范](#contexthttp_request-详细规范)
11. [使用秘密（来自包）](#使用秘密（来自包）)
12. [使用能力](#使用能力)
13. [存储 API（通过功能）](#存储-api（通过功能）)
14.【Inter-Pack合作模式】(#跨包装合作模式)
15.§鲁米§0§
16. [pip 依赖项（requirements.lock）](#pip-依赖项（requirementslock）)
17.§鲁米§0§
18. [包括能力处理程序](#includes-capability-handler)
19.§鲁米§0§
20. [组件（高级）](#组件（高级）)
21. [包特定端点 (routes.json)](#特定于包的端点-routesjson)
22. [HTTP状态码控制](#http状态码控制)
23. [错误处理最佳实践](#错误处理最佳实践)
24. [流动调节器推荐模式](#流量调节剂推荐模式)
25. [Handler API 分类](#处理程序api分类)
26. [输出键命名约定（详情）](#输出键命名约定（详情）)
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
4. **写入流程** — 放置在打包和连接块中的`user_data/shared/flows/`或`flows/`中
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

> **关于路径**：`ecosystem/<pack_id>/`是推荐路径。 `ecosystem/packs/<pack_id>/` 也支持作为兼容路径，但如果两者中存在相同的`pack_id`，则`ecosystem/<pack_id>/` 优先。

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

|领域 |必填 |描述 |
|-----------|------|------|
| §鲁米§0§| ✅ |包标识符。匹配目录名称|
| §鲁米§0§| ✅ |经销商标识符（例如`github:author/repo`）。如果此值在 Pack 更新期间发生变化，则应用将被拒绝 |
| §鲁米§0§|可选|语义版本控制 |
| §鲁米§0§|可选|描述 |
| §鲁米§0§|可选| Pack 使用的词汇列表。用于与 vocab.txt 协作 |
| §鲁米§0§|可选|所需密钥列表（例如`["OPENAI_API_KEY"]`）。用于向用户提供信息|
| §鲁米§0§|可选|网络要求（例如`{"allowed_domains": ["api.example.com"], "allowed_ports": [443]}`）。用于向用户提供信息|
| §鲁米§0§|可选|需要主机执行（`true` / `false`）。对于`true`，作为主机进程运行而不是容器隔离 |

### 连接性（包间依赖声明）

您可以通过将`connectivity`字段添加到`ecosystem.json`来声明包之间的依赖关系。

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

|领域 |描述 |
|-----------|------|
| §鲁米§0§|此包提供的服务名称列表|
| §鲁米§0§|此包所需的服务名称列表 |

连接`requires`/`provides`用于在启动时自动解析包加载顺序（load_order）。首先加载`provides` `requires` 中指定的服务的包。

如果存在手动规范（`load_order``ecosystem.json`字段），则优先。仅在没有手动指定的情况下才应用自动解析。

目前，连接的唯一运行时影响是自动加载顺序解析。未来可能会扩大。

#### 连接模式示例

|提供 |意义|典型包装|
|----------|------|--------------|
| §鲁米§0§|人工智能API客户端| OpenAI / Anthropic 客户端 |
| §鲁米§0§|工具注册|工具管理器|
| §鲁米§0§|内存存储|内存管理|
| §鲁米§0§|聊天界面 |前端 |

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

`run` 函数还仅允许`input_data` 的单参数版本。

### 返回值

请返回 JSON 兼容的字典。返回的值按原样存储在流的`output`字段中指定的上下文键中。内核内部的包装器（例如`_kernel_step_status`）会自动删除，并且块返回的值直接进入`ctx[output_key]`。

### 输出键命名约定

以下规则适用于存储在流程步骤的`output`中的值的键名称。

以`_`前缀开头的键被保留为内核内部键。如果`run()`或`python_file_call`返回的字典包含带有`_`前缀的键（例如`_kernel_step_status`，`_debug`），则它们在存储在Flow的`output`上下文中时将被自动排除。

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

由`python_file_call`调用的`run()`函数接受以下三种模式之一。执行引擎自动检测`inspect.signature`中的参数数量。

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

| JSON 类型 | Python 类型 |
|---------|----------|
|对象| §鲁米§0§|
|数组| §鲁米§0§|
|字符串| §鲁米§0§|
|数字（整数）| §鲁米§0§|
|数字（十进制）| §鲁米§0§|
|布尔 | §鲁米§0§|
|空 | §鲁米§0§|

`input_data` 本身通常是`dict`，但如果您直接在流定义中指定标量值或列表，它将属于该类型。

### 上下文类型

`context` 是`dict[str, Any]`。主要按键是：

|关键|类型 |描述 |
|------|----|------|
| §鲁米§0§| §鲁米§1§ |运行流程 ID |
| §鲁米§0§| §鲁米§1§ |正在运行的步骤 ID |
| §鲁米§0§| §鲁米§1§ |执行阶段名称|
| §鲁米§0§| §鲁米§1§ |执行开始时间戳（ISO 8601 UTC）|
| §鲁米§0§| §鲁米§1§ |拥有的包 ID |
| §鲁米§0§| §鲁米§1§ |与 input_data | 相同
| §鲁米§0§| §鲁米§1§ | HTTP请求函数(参见[context\["http\_request"\]详细规范](#contexthttp_request-详细规范)) |
| §鲁米§0§| §鲁米§1§ |网络访问检查功能|
| §鲁米§0§| §鲁米§1§ | UDS 套接字路径功能 |

### 返回类型

`run()`的返回值必须是JSON可序列化值（`dict`、`list`、`str`、`int`、`float`、`bool`、`None`）。如果您返回`None`，则流输出将被视为`null`。如果返回值为`dict`，则其内容存储在流的`output`变量中。

### 验证最佳实践

`input_data` 的内容源自外部来源（流程定义和用户输入），因此请务必验证它们。

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

- 返回`{"error": "..."}`并正常退出，而不是抛出异常。
- 检查函数开头的所有必填字段
- 严格按照`isinstance()`检查类型
- 设置数字范围和列表长度的限制

---

## 流程定义

### 放置路径

|路径|目的|
|------|------|
| §鲁米§0§|分享流程。适合跨多个电池组接线 |
| §鲁米§0§|特定于包的流程 |

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

|领域 |必填 |描述 |
|-----------|------|------|
| §鲁米§0§| ✅ |步骤 ID（流程中唯一）|
| §鲁米§0§| ✅ |隶属阶段 |
| §鲁米§0§|可选|执行优先级（升序；默认 100） |
| §鲁米§0§| ✅ | §鲁米§1§ |
| §鲁米§0§|可选|拥有的包（如果从路径推断可以省略）|
| §鲁米§0§| ✅ |可执行文件的相对路径 |
| §鲁米§0§|任何 |输入数据（可进行变量扩展）|
| §鲁米§0§|可选|输出目标上下文键 |
| §鲁米§0§|可选|超时秒数（默认 60）|

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

####设置

```yaml
- id: set_default
  phase: prepare
  priority: 5
  type: set
  input:
    key: "model"
    value: "gpt-4"
```

> **注意**：`set`类型由在InterfaceRegistry中注册的`flow.construct.set`处理程序处理。 Flow 加载器将`set` 解释为标准步骤类型，但执行是通过构造进行的。 `set` 如果构造未注册，则跳过该步骤。

####流（子流调用）

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

`flow`类型将另一个流称为子流。递归调用（循环引用）会被自动检测并导致错误。子流的上下文是从父流深度复制的，并添加`args`中指定的值。

####函数（能力函数调用）

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

`function`类型执行通过`capability_executor`在FunctionRegistry中注册的函数。在`function`字段中指定`permission_id`（例如，`store.get`）。执行需要相应的能力授予。

|领域 |必填 |描述 |
|-----------|------|------|
| §鲁米§0§| ✅ | §鲁米§1§ |
| §鲁米§0§| ✅ |要执行的函数的permission_id（例如`store.get`，`docker.run`）|
| §鲁米§0§|任何 |函数的参数（可以进行变量扩展）|
| §鲁米§0§|可选|输出目标上下文键 |
| §鲁米§0§|可选|对于`true`，在求解之前 vocab 对`function` 的值进行归一化 |

### 变量扩展

您可以使用`${ctx.key}`引用上下文中的值。嵌套引用 (`${ctx.user.id}`) 也是可能的。如果引用不存在，则为`null`。

### 安排执行

通过将`schedule`字段添加到流程中可以定期执行。

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

cron 表达式支持`*`、`*/N`、数字、逗号分隔、范围 (`N-M`) 和范围+步长 (`N-M/S`)。调度程序以每 10 秒的时钟周期为单位进行评估，因此 cron 的精度以分钟为单位。自动防止同一流程的重复执行。

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

当Pack的`routes.json`中定义的端点接收到HTTP请求时，Pack API服务器（`pack_api_server.py`）执行相应的流程，将结果转换为HTTP响应，然后返回。

### 响应转换的工作原理

在当前实现中，流程执行结果（`outputs`）**始终以 JSON 格式返回**。响应是通过`APIResponse`数据类生成的。

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

|状态 |状态代码 |
|------|-----------------|
|流程执行成功 | §鲁米§0§|
|认证失败 | §鲁米§0§|
|输入无效 | §鲁米§0§|
|未找到路线 | §鲁米§0§|
|内部错误 | §鲁米§0§|

### 标题

以下标头会自动添加到响应中。

|标题|价值|状况 |
|---------|-----|------|
| §鲁米§0§| §鲁米§1§ |总是被授予|
| §鲁米§0§|由原产地要求 |匹配 CORS 允许列表 |
| §鲁米§0§| §鲁米§1§ |添加 CORS 标头时 |

### 使用特殊键控制

目前 **不支持** 使用特殊键（例如`_status_code`、`_headers`、`_body`）直接控制 HTTP 响应。流输出始终存储在`APIResponse`的`data`字段中，并以`application/json`格式返回。

如果您需要自定义状态代码或标头控制，请参阅[HTTP 状态代码控制](#http状态码控制)。

---

## 流量调节器

这是一种稍后将函数插入现有流程的机制。

### 放置路径

- §鲁米§0§
- §鲁米§0§

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

|行动|描述 |
|--------|------|
| §鲁米§0§|在指定步骤之前插入 |
| §鲁米§0§|在指定步骤后插入 |
| §鲁米§0§|添加到阶段结束 |
| §鲁米§0§|替换指定步骤 |
| §鲁米§0§|删除指定步​​骤 |

> **阶段约束**：修改器的`phase`必须包含在目标流的`phases`列表中。如果指定不存在的阶段，则将跳过修改器。

> **应用顺序**：修饰符按阶段→优先级→modifier_id排序并确定性应用。如果同一注入点有多个修饰符（`inject_before` / `inject_after` 到同一个`target_step_id`），它们会按照优先级→step.id→modifier_id 的顺序一次性插入，以防止由于索引移位而导致的不确定性。 `replace` / `remove` 在注入/附加之前应用。

### 通配符 target_flow_id

您可以在`target_flow_id`中使用通配符模式将修饰符同时应用于多个流。

|图案|意义|
|----------|------|
| §鲁米§0§|适用于所有流程 |
| §鲁米§0§|适用于以`my_pack.` 开头的所有流程 |

Python 的`fnmatch` 用于匹配。

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

###需要条件

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

包在 Docker `--network=none` 中被隔离，无法直接与外部通信。外部通信需要网络授权，所有请求都通过出口代理（UDS 套接字）。

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

在`python_file_call`的`run(input_data, context)`中传递的`context["http_request"]`是Pack代码进行外部HTTP通信的唯一方式。

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

|参数|类型 |默认 |描述 |
|------------|-----|-----------|------|
| §鲁米§0§| §鲁米§1§ | （必填）| HTTP 方法。 `GET`、`POST`、`PUT`、`DELETE`、`PATCH`、`HEAD` |
| §鲁米§0§| §鲁米§1§ | （必填）|请求的完整 URL |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ | HTTP 请求标头 |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |请求正文（字符串）。发送 JSON 时，传递`json.dumps()` 字符串 |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |超时秒数。限制最多`120.0`秒 |

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

|错误类型 |描述 |
|------------|------|
| §鲁米§0§|未找到出口代理套接字 |
| §鲁米§0§|没有权限访问套接字|
| §鲁米§0§|与出口代理的连接被拒绝 |
| §鲁米§0§|请求超时 |
| §鲁米§0§|协议级错误 |
| §鲁米§0§|响应 JSON 解析失败 |
| §鲁米§0§|由于网络授权而拒绝访问 |

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

> 可以使用`RUMI_EGRESS_SOCK_DIR`环境变量更改套接字路径。默认为`/run/rumi/egress/packs`。

### 容器模式和主机模式的区别

|项目 |容器模式（严格）|主机模式（宽容）|
|------|--------------------------|---------------------------|
|网络| `--network=none`（完全隔离）|使用主机网络 |
|通讯路径|仅通过 UDS 套接字 |通过 UDS 套接字（通过辅助函数）|
|套接字路径 | `/run/rumi/egress/packs/{pack_id}.sock`（集装箱内安装）| §鲁米§1§ |
|拨款验证 |出口代理已验证 |出口代理已验证 |
|安全| Docker 隔离 + UDS 限制 |运行时出现警告（不建议用于生产）|

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

包使用`secrets.get` 能力来获取秘密（例如 API 密钥）。在运营商注册秘密并授予资助后，它就变得可用。

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

|权限 ID |处理程序 ID |描述 |风险|
|---------------|-----------|------|------|
| §鲁米§0§| §鲁米§1§ |获取秘密价值 |高|
| §鲁米§0§| §鲁米§1§ |从 Store 读取值 |低|
| §鲁米§0§| §鲁米§1§ |将值写入 Store |中等|
| §鲁米§0§| §鲁米§1§ |从 Store 中删除一个值 |中等|
| §鲁米§0§| §鲁米§1§ |获取商店中的钥匙列表 |低|
| §鲁米§0§| §鲁米§1§ |从商店批量检索（最多 100 个键）|低|
| §鲁米§0§| §鲁米§1§ | Store Compare-And-Swap（乐观独占控制）|中等|
| §鲁米§0§| §鲁米§1§ |发送 JSON 消息到其他 Pack 组件的收件箱 |中等|
| §鲁米§0§| §鲁米§1§ |建议对其他包进行文件更改（暂存创建，无自动应用）|高|
| §鲁米§0§| §鲁米§1§ |同步流到流调用 |中等|
| §鲁米§0§| §鲁米§1§ | Docker 容器执行 | — |
| §鲁米§0§| §鲁米§1§ | Docker 容器内的命令执行 | — |
| §鲁米§0§| §鲁米§1§ |停止 Docker 容器 | — |
| §鲁米§0§| §鲁米§1§ | Docker容器日志获取 | — |
| §鲁米§0§| §鲁米§1§ | Docker 容器列表 | — |

### 格兰特 格兰特

补助金由使用 API 的用户或运营商授予。有关详细信息，请参阅[operations.md](./operations.md)中的“能力授予管理”。

```bash
# 例: store.get の Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["my_store"]}}'
```

### 授予配置（grant_config）

补助金可以在`config`中设置限制。设置因权限而异。

|权限 ID | grant_config 密钥 |描述 |
|---------------|-------------------|------|
| §鲁米§0§| §鲁米§1§ |可访问的键名称列表（必需，如果为空则完全拒绝）|
| §鲁米§0§| §鲁米§1§ |可访问的 store_ids 列表（必填，如果为空则完全拒绝）|
| §鲁米§0§| §鲁米§1§ |最大写入大小（字节，默认 1MB）|

`allowed_keys` / `allowed_store_ids` 是故障关闭的。如果列表为空或未指定，则所有访问都将被拒绝。

### 错误处理

如果功能调用失败，则返回包含`success: False`的字典。

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

|错误类型 |描述 |
|------------|------|
| §鲁米§0§| Pack 没有授予权限 |
| §鲁米§0§|处理程序的 sha256 未在信任存储中注册 |
| §鲁米§0§|指定permission_id对应的handler不存在 |
| §鲁米§0§|运行处理程序时出错 |
| §鲁米§0§|执行超时 |
| §鲁米§0§|未找到功能插座 |

---

## 存储 API（通过功能）

### 概述

Store 是可以在 Pack 之间共享的键值存储。存储操作是通过 Capability 执行的。当操作员向包授予能力授权时，将启用访问权限。

### 可用的permission_id

|权限 ID |描述 |参数|
|---------------|------|------|
| §鲁米§0§|从 Store | 读取值§鲁米§1§，§鲁米§2§|
| §鲁米§0§|将值写入存储 | §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|从商店中删除价值 | §鲁米§1§，§鲁米§2§|
| §鲁米§0§|获取商店中的钥匙列表 | `store_id`、`prefix`（可选）|

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

`store.*` 中的补助金可以在 `grant_config` 中设置限制：

| grant_config 密钥 |描述 |默认 |
|-------------------|------|-----------|
| §鲁米§0§|允许访问的 store_ids 列表 | `[]`（如果列表为空，则拒绝访问所有 Store。必须显式指定 Store_id 才能访问）|
| §鲁米§0§| `store.set` 最大大小（字节）| 1MB (1048576) |

`allowed_store_ids` 失败关闭。如果您在创建授权时未指定`allowed_store_ids`或指定空列表`[]`，则该授权将拒绝访问所有商店。对于要访问 Store 的 Pack，操作员必须显式地将 store_id 添加到列表中。

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

|权限 ID |处理程序 ID |描述 |风险|
|---------------|-----------|------|------|
| §鲁米§0§| §鲁米§1§ |获取秘密价值 |高|
| §鲁米§0§| §鲁米§1§ |从 Store 读取值 |低|
| §鲁米§0§| §鲁米§1§ |将值写入 Store |中等|
| §鲁米§0§| §鲁米§1§ |从 Store 中删除一个值 |中等|
| §鲁米§0§| §鲁米§1§ |获取商店中的钥匙列表 |低|
| §鲁米§0§| §鲁米§1§ |从商店批量检索（最多 100 个键）|低|
| §鲁米§0§| §鲁米§1§ | Store Compare-And-Swap（乐观独占控制）|中等|
| §鲁米§0§| §鲁米§1§ |发送 JSON 消息到其他 Pack 组件的收件箱 |中等|
| §鲁米§0§| §鲁米§1§ |建议对其他包进行文件更改（暂存创建，无自动应用）|高|
| §鲁米§0§| §鲁米§1§ |同步流到流调用 |中等|
| §鲁米§0§| §鲁米§1§ | Docker 容器执行 | — |
| §鲁米§0§| §鲁米§1§ | Docker 容器内的命令执行 | — |
| §鲁米§0§| §鲁米§1§ |停止 Docker 容器 | — |
| §鲁米§0§| §鲁米§1§ | Docker容器日志获取 | — |
| §鲁米§0§| §鲁米§1§ | Docker 容器列表 | — |

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

|关键|描述 |
|------|------|
| §鲁米§0§|包装 ID |
| §鲁米§0§| `"install"` 或 `"update"` |
| §鲁米§0§|时间戳|
| §鲁米§0§| lib 目录路径（容器内：`/lib`）|
| §鲁米§0§|可写目录（在容器中：`/data`，主机：`user_data/packs/{pack_id}/`）|

### 安全限制

在严格模式下，它在 Docker 容器内隔离运行。 §鲁米§0§，§鲁米§1§。只能写入`/data`（=`user_data/packs/{pack_id}/`）。

---

## pip 依赖项 (requirements.lock)

### 概述

如果您的包依赖于 PyPI 包，请包含`requirements.lock`。

### 放置路径

按以下顺序搜索：

1.§鲁米§0§
2.`<pack_subdir>/backend/requirements.lock`（兼容）

### 格式

仅允许使用`NAME==VERSION` 行。允许注释行和空行。

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

在执行容器中，站点包安装为`/pip-packages:ro`，并添加到`PYTHONPATH`。

### 如何获得批准

用户或运营商通过API批准。有关更多信息，请参阅[operations.md](./operations.md)中的“pip依赖库管理”。

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

将其放在包装的`pack_subdir`（通常为`ecosystem/<pack_id>/backend/`）下的`share/capability_handlers/<slug>/`中。

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

|领域 |必填 |描述 |
|-----------|------|------|
| §鲁米§0§| ✅ |处理程序的唯一标识符 |
| §鲁米§0§| ✅ |请求的权限 ID |
| §鲁米§0§| ✅ |执行入口点（例如`handler.py:execute`）|
| §鲁米§0§|可选|描述 |
| §鲁米§0§|可选|风险描述|

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

|领域 |必填 |描述 |
|-----------|------|------|
| §鲁米§0§| ✅ |函数标识符 |
| §鲁米§0§|可选|功能说明|
| §鲁米§0§| ✅ |运行此功能所需的permission_ids列表（例如`["store.get"]`）|
| §鲁米§0§|可选|向调用者请求的附加权限列表 |
| §鲁米§0§|可选|如果`true`，则在主机进程而不是容器中运行 |
| §鲁米§0§|可选|分类标签列表 |
| §鲁米§0§|可选|风险级别（`low`、`medium`、`high`）。 docker type | 等一些函数中省略了它
| §鲁米§0§|可选|用于词汇规范化的别名列表 |
| §鲁米§0§|可选|输入 JSON 架构 |
| §鲁米§0§|可选|输出 JSON 架构 |
| §鲁米§0§|可选| Grant 的默认设置（用于 docker 系统） |
| §鲁米§0§|可选|调用约定。 `block`（默认，core_pack 标准）= `execute(context, args)` 模式 |

> **注意**：manifest.json 中不存在`permission_id` 字段。使用`requires`数组指定权限。

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

如果`calling_convention`是`block`（默认），入口点是`execute(context, args)`。 `context`包含诸如`grant_config`之类的执行信息，并且`args`被传递在流程步骤的`input`中指定的值。

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

包可以包含`routes.json`以在HTTP API服务器上注册它们自己的端点。接收到的请求执行指定的Flow并将结果作为响应返回。

### 放置路径

§鲁米§0§

###routes.json 格式

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

示例：如果您请求`/api/orgs/{org_id}/tasks/{task_id}`，`inputs.org_id`和`inputs.task_id`将有它们各自的值。

### 获取查询参数

GET 请求的查询参数也包含在`inputs`中。

### 获取原始正文/标头

Flow 的`inputs` 还包括以下特殊键：

|关键|描述 |
|------|------|
| §鲁米§0§|请求正文的base64编码值|
| §鲁米§0§|请求标头的字典 |
| §鲁米§0§| HTTP 方法（GET、POST 等）|
| §鲁米§0§|请求路径|

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

即使您在流的输出中包含特殊键（例如`_status_code`），它也只会包含在响应的`data`字段中，而不会反映在HTTP状态代码中。

### 状态码判断逻辑

Pack API Server 使用以下逻辑确定状态代码。

|判决令 |状态 |状态码 |
|--------|------|-----------------|
| 1 |认证失败 | §鲁米§0§|
| 2 |输入验证失败 | §鲁米§0§|
| 3 |未找到路线 | §鲁米§0§|
| 4 |流程执行成功 | `200`（已修复）|
| 5 |运行 Flow 时返回错误字典 | `200`（数据包含错误，但 HTTP 为 200）|
| 6 | Flow执行过程中出现异常 | §鲁米§0§|

这意味着即使流程成功完成并返回`{"error": "not found"}`，HTTP 状态代码也将为`200 OK`。

### 推荐图案

在当前限制下，使用响应正文中的`success` 和`error` 字段将错误传达给客户端。

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

在未来的版本中，我们正在考虑添加识别 Flow 输出中的特殊键（`_status_code`、`_headers`等）的功能，并将其反映在 HTTP 响应中。

---

## 错误处理最佳实践

### 如果 python_file_call 的 run() 发生异常

`run()` 当函数内发生未捕获的异常时，执行引擎将执行以下操作：

**容器模式**：Docker 进程以非零退出代码退出，并且 stderr 的内容被记录为错误消息。 `ExecutionResult` 中的`success` 变为`False`，`error_type` 变为`"container_execution_error"`。

**主机模式（宽容）**：异常从`ThreadPoolExecutor`中的`Future`传播，类似地，`ExecutionResult`中的`success`变成`False`。

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

|设置|行为 |
|------|------|
| `defaults.fail_soft: true`（默认）|记录步骤失败并继续下一步 |
| §鲁米§0§|当某个步骤失败时中断整个流程 |
| §鲁米§0§|如果此步骤失败则中止流程 |
| §鲁米§0§|即使此步骤失败也继续 |
| §鲁米§0§|禁用目标并继续 |

如果流程级别错误处理程序在 InterfaceRegistry 中注册为`flow.error_handler`，则当步骤异常发生时，将调用该处理程序。错误处理程序可以通过返回`"abort"`（中止）、`"retry"`（重试）或其他内容（继续）来控制行为。

### 在capability.call()失败的情况下如何处理返回值

如果您通过`rumi_capability`模块调用Capability，则失败时将返回包含`success: False`的字典。

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

|错误类型 |描述 |
|------------|------|
| §鲁米§0§|未获授权使用功能 |
| §鲁米§0§|未授予能力补助金 |
| §鲁米§0§|信任库验证失败 |
| §鲁米§0§|指定的功能处理程序不存在 |
| §鲁米§0§|运行 Handler | 时发生错误
| §鲁米§0§|执行超时 |
| §鲁米§0§|未找到功能插座 |

我们建议您使用返回值的`success`字段检查这些错误，而不是使用try- except。

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

|处理程序 |描述 |如何在 Flow 中使用 |
|---------|------|----------------|
| §鲁米§0§|运行Python文件 | §鲁米§1§ |
| §鲁米§0§|呼叫子流程| §鲁米§1§ |
| §鲁米§0§|执行能力功能| §鲁米§1§ |
| §鲁米§0§|在上下文中设置值 | §鲁米§1§ |
| §鲁米§0§|直接调用注册的handler | §鲁米§1§ |

### 内部 API（Pack 开发人员不使用）

用于内部内核操作的处理程序。包开发人员不需要直接调用这些。

|类别 |示例 |描述 |
|---------|-----|------|
| §鲁米§0§| §鲁米§1§，§鲁米§2§|内核中的上下文操作 |
| §鲁米§0§| §鲁米§1§，§鲁米§2§|流生命周期钩子 |
| §鲁米§0§| §鲁米§1§，§鲁米§2§| Flow语法的内部实现 |
| §鲁米§0§| §鲁米§1§，§鲁米§2§|组件生命周期|

> **注意**：内部 API 如有更改，恕不另行通知。不要直接从 Pack 的 Flow 定义中引用这些内容。

---

## 输出键命名约定（详细）

### 内核内部键排除规则

当流程执行结果作为 HTTP 响应返回时，以以下前缀开头的键将自动排除为 **内核内部键**。

|前缀|描述 |
|---------------|------|
| §鲁米§0§|流量控制信息|
| §鲁米§0§|内核步骤元数据 |
| §鲁米§0§|步进输出内部参考|
| §鲁米§0§|当前步数 |
| §鲁米§0§|总步数 |
| §鲁米§0§|家长流程信息|
| §鲁米§0§|执行者 ID |
| §鲁米§0§|流量控制信号|
| §鲁米§0§|错误信息 |
| §鲁米§0§|流量默认值|

### 如果包开发者返回`_`前缀键

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
- 如果您想包含调试信息，请使用常规键名称，例如`debug`或`metadata`
- 应特别避免与内核内部前缀匹配的键名称（例如`_flow_result`），因为它们会被无意中排除。

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

- **InterfaceRegistry 是一个内部 API。 ** 请勿直接从包装上操作 IR。
- **外部通信必须通过出口代理完成**。使用`context["http_request"]`。
- **lib 只能写入`/data`。 ** 由于`--read-only`，写入任何其他路径都会失败。
- 不要更改 **pack_identity。 ** 如果更新期间`pack_identity`发生变化，申请将被拒绝。
- **principal_id在v1中被强制被owner_pack覆盖。 ** 即使您在流定义或修饰符中指定`principal_id`，`owner_pack` 的值也将在运行时用作主体。如果检测到差异，则会在审核日志中记录一条警告。
- **关于响应大小限制**：出口代理 (`rumi_syscall`) 和功能客户端 (`rumi_capability`) 的响应限制为 4MB（可在`RUMI_MAX_RESPONSE_BYTES` 中更改）。但是，Capability Executor（服务器端子进程执行）的响应限制为 1MB。
- **store.set 的默认值大小限制为 1MB。 ** 可以通过 Grant 的`grant_config.max_value_bytes` 进行更改。
- **FlowScheduler 的最小间隔值为 10 秒。 ** 如果您指定的时间少于 10 秒，则会向上舍入到接下来的 10 秒。
- **同时执行 Flow 的默认数量为 10。 ** 可以使用`RUMI_MAX_CONCURRENT_FLOWS`环境变量进行更改。
- **功能执行超时限制为 120 秒。 ** 即使您为`rumi_capability.call()`的`timeout_seconds`指定大于120的值，它也会被限制为120秒。默认值为 30 秒。

### 不支持硬链接

**不支持**在 Pack 目录 (`ecosystem/<pack_id>/`) 中使用硬链接。

####原因

Pack 授权/哈希验证系统使用以`Path.resolve()` 规范化的文件路径作为缓存密钥。符号链接通过`resolve()`解析为真实路径，因此源和目标被组合到同一个缓存条目中。另一方面，硬链接在`resolve()`中并不统一（每个路径条目保持独立）。因此，指向同一 inode 的多个路径被视为单独的缓存条目，并且通过一个路径对文件的更改可能不会反映在另一路径上的哈希验证中。

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

- **符号链接**：解析为`resolve()`中的真实路径，使其与哈希验证一致。但是，符号链接的引用目标仅限于 **pack_subdir 边界内**。指向边界之外的符号链接在运行时会被拒绝。
- **文件复制**：最安全的方法。每个文件都有独立的哈希值，不存在验证问题。

---

## API 参考

### rumi_syscall（外部通信）

这是一个用于从容器内执行外部 HTTP 通信的模块。用于`import rumi_syscall`。

|功能|描述 |
|------|------|
| §鲁米§0§|通用 HTTP 请求 |
| §鲁米§0§|获取快捷方式 |
| §鲁米§0§|发布快捷方式 |
| §鲁米§0§| JSON POST 快捷方式（Content-Type 自动设置）|
| §鲁米§0§| PUT 快捷方式 |
| §鲁米§0§|删除快捷方式 |
| §鲁米§0§|补丁快捷方式|
| §鲁米§0§| HEAD 快捷方式 |

返回值是一个包含`success`（bool），`status_code`（int），`headers`（dict），`body`（str），`error`（str），`error_type`（str），`latency_ms`（float），`redirect_hops`（int），`bytes_read`（int），`final_url`的字典（str）等

`request` 是`http_request` 的别名。 `rumi_syscall.request(...)` 具有相同的行为。

### rumi_capability（功能调用）

用于从容器内调用功能的模块。用于`import rumi_capability`。

|功能|描述 |
|------|------|
| §鲁米§0§|执行能力|

返回值是一个包含`success`（bool）、`output`（Any）、`error`（str）、`error_type`（str）、`latency_ms`（float）的字典。

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

Defaultspack 功能可作为 Rumi 函数使用。首选调用别名，例如`defaults.ai.complete`、`defaultspack.chat.send`或`defaultspack.ai.set_thinking_level`，而不是依赖于 HTTP 路由或默认包文件路径。有关示例、权限和 AI 工具包装指南，请参阅[defaultspack-functions.md](defaultspack-functions.md)。
