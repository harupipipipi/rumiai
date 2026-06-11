<!-- docs-i18n-links:start -->
[EN](../../../internals/block-signature.md) | [JP](../../ja/internals/block-signature.md) | [KR](../../ko/internals/block-signature.md) | [CN](./block-signature.md)
<!-- docs-i18n-links:end -->

# 区块签名规范

默认包中的所有块都放置在`blocks/<category>/<name>.py`中并遵循统一的签名。

---

## `def run(input_data, context)` 规则

每个块在模块级别导出一个具有以下签名的`run`函数：

```python
def run(input_data: dict, context: dict) -> dict:
```

### input_data 的结构

`input_data` 是一个存储来自客户端的请求数据的字典。传递到传输层后会做以下事情：

在 HTTP 的情况下，作为解析的 JSON Body 的字典按原样传递。路径参数由传输层预先注入到`input_data`中。例如，对于`/api/chat/conversations/{id}`：

```python
input_data["conversation_id"] = path_params.get("id", "")
```

对于 stdio/UDS，将传递请求 JSON 的`"data"`字段的内容。路径参数的注入是根据`_ID_INJECT_MAP`自动完成的。

`input_data`中包含的字段因每个块而异。每个块使用`input_data.get()`获取其需要的字段，如果不足则返回`error()`。

### 上下文的所有字段

#### 直接调用时的传输字段

由`_build_context()`为每个传输生成的基字段。每次通话时都必须在场。

|领域 |类型 |描述 |
|---|---|---|
| `flow_id`| `string` |执行流程标识符。直接调用时，`"transport_direct"` (HTTP)、`"stdio_direct"` (stdio) 或`"uds_direct"` (UDS) |
| `step_id`| `string` |步骤的标识符。直接调用时，`"http_request"` (HTTP)、`"stdio_request"` (stdio) 或`"uds_request"` (UDS) |
| `phase`| `string` |总是`"execute"` |
| `ts`| `string` | ISO 8601 时间戳（例如`"2025-01-01T00:00:00Z"`）|
| `owner_pack`| `string` |总是`"defaults"` |
| `inputs`| `dict` |附加输入。通常为空字典 |

#### 通过 Flow 引擎/内核添加的字段

当通过 Flow 引擎或通过 `call_handler` 调用处理程序时，内核会将以下附加字段注入到上下文中： 直接调用传输时这些字段不存在（处理程序必须使用 `context.get()` 安全地检索它们）。

|领域 |类型 |描述 |
|---|---|---|
| `call_handler`| `callable \| None` |调用其他处理程序的函数。 `call_handler(handler_name: str, input_data: dict) -> dict` 的签名。通过内核的 InterfaceRegistry 解析处理程序名称并调用目标`run()` |
| `emit_event`| `callable \| None` |触发事件的函数。 `emit_event(event_type: str, data: dict) -> None` 的签名。发送事件到内核的EventBus |
| `wait_event`| `callable \| None` |等待事件的函数。 `wait_event(event_type: str, timeout: int, filter: dict) -> dict \| None` 的签名。阻止直到指定的事件触发 |
| `emit_widget`| `callable \| None` |将 Widget 发送到 UI 的函数。 `emit_widget(widget_json: dict) -> None` 的签名。发送第 `lib/rumi_widgets/` | 中定义的 Widget 结构
| `cancel_check`| `callable \| None` |检查当前执行是否已取消的函数。 `cancel_check() -> bool` 的签名。在长时间运行的循环中定期调用它并使用它来提前终止 |
| `handler_config`| `dict \| None` |处理程序配置信息。 `conditions.json` 等中定义的处理程序特定设置是从内核注入的 |
| `session`| `dict \| None` |会话信息。包含`session_id`、`workspace`等字段。用于会话范围状态管理 |

#### 使用上下文字段的示例

```python
def run(input_data, context):
    # transport 直接呼び出し時のベースフィールド（常に存在）
    flow_id = context["flow_id"]
    ts = context["ts"]

    # Flow エンジン経由のフィールド（存在しない場合がある）
    call_handler = context.get("call_handler")
    emit_event = context.get("emit_event")
    emit_widget = context.get("emit_widget")
    cancel_check = context.get("cancel_check")
    session = context.get("session")
    handler_config = context.get("handler_config")

    # call_handler が存在する場合のみ他の handler を呼び出す
    if call_handler is not None:
        result = call_handler("defaults.ai.complete", {
            "model": "openai/gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
        })

    # cancel_check が存在する場合のみキャンセルチェック
    if cancel_check is not None and cancel_check():
        return error("execution cancelled", "CANCELLED")

    return ok({"done": True})
```

---

## 返回值 — `ok()` / `error()` 格式

所有块都使用`blocks/_common.py`、`ok()`或`error()`返回结果。

### 成功响应

```python
from blocks._common import ok

return ok({"key": "value"})
# → {"status": "ok", "data": {"key": "value"}}

return ok(None)
# → {"status": "ok", "data": null}
```

### 错误响应

```python
from blocks._common import error

return error("conversation_id is required", "INVALID_INPUT")
# → {"status": "error", "error": {"code": "INVALID_INPUT", "message": "conversation_id is required"}}

return error("something went wrong")
# → {"status": "error", "error": {"code": "ERROR", "message": "something went wrong"}}
```

### 未实现的存根

```python
from blocks._common import not_implemented

return not_implemented("defaults.some.handler")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.some.handler"}
```

### 静态文件（仅适用于transport/http.py）

只有 HTTP 传输具有返回静态文件的特殊格式：

```python
return {"_static": True, "content_type": "text/html; charset=utf-8", "body": "<html>...</html>"}
```

---

## 导入路径规则

所有块文件都在开头设置`sys.path`，格式如下：

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
```

这允许您使用包根目录的绝对路径导入：

```python
from blocks._common import ok, error, gen_id, timestamp
from domain.chat.store import ChatStore
from domain.ai_client.client import AIClient
```

`sys.path.insert(0, ...)` 应写在文件的开头（在其他导入之前）。

---

## `_common.py`的所有功能

`blocks/_common.py`提供以下五种功能：

### `ok(data=None) -> dict`

返回成功响应。将任何 JSON 可序列化对象传递给`data`。

```python
ok({"id": "abc"})   # → {"status": "ok", "data": {"id": "abc"}}
ok()                 # → {"status": "ok", "data": null}
```

### `error(message, code="ERROR") -> dict`

返回错误响应。

```python
error("not found", "NOT_FOUND")  # → {"status": "error", "error": {"code": "NOT_FOUND", "message": "not found"}}
error("fail")                     # → {"status": "error", "error": {"code": "ERROR", "message": "fail"}}
```

### `not_implemented(handler_name) -> dict`

返回未实现的处理程序的存根响应。

```python
not_implemented("defaults.foo.bar")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.foo.bar"}
```

### `timestamp() -> str`

返回 ISO 8601 格式的 UTC 时间戳字符串。

```python
timestamp()  # → "2025-01-01T00:00:00Z"
```

内部实施：`time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())`

### `gen_id() -> str`

返回 UUID v4 字符串。

```python
gen_id()  # → "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

内部实施：`str(uuid.uuid4())`
