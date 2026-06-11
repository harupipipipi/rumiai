<!-- docs-i18n-links:start -->
[EN](../../transport.md) | [JP](../ja/transport.md) | [KR](../ko/transport.md) | [CN](./transport.md)
<!-- docs-i18n-links:end -->

# 传输层

defaultspack 提供三种类型的传输作为与前端和客户端通信的方式。两者都位于`transport/`目录中。

---

## 概述

传输层是一个中间层，它接收来自客户端的请求，解析`transport/registry.py`中的端点->流/函数声明，并返回响应。通常，聊天主线经过`defaultspack.chat_turn` / `defaultspack.chat_stream_turn`，现有前端的HTTP路径、JSON形状和SSE事件形状保持与后备块的向后兼容性。 `ecosystem/defaults/transport/*` 是默认包传输的兼容性填充程序。

传输选择在启动时确定。 `defaults.frontend.start`处理程序根据`transport`参数启动适当的传输。

---

## HTTP 服务器 (`transport/http.py`)

### 默认HttpServer

`DefaultsHttpServer` 是基于 Python 标准库`http.server.HTTPServer` 的 HTTP 服务器。

```python
from transport.http import start_http_server

server = start_http_server(facade)  # KernelFacade or None
```

**构造函数参数：**

`facade` — 内核的 KernelFacade 实例。 `/api/context` 用于在端点上调用`list_interfaces()`。也不可能。

**环境变量：**

`DEFAULTS_HTTP_HOST` — 绑定主机。默认`127.0.0.1`。
`DEFAULTS_HTTP_PORT` — 绑定端口。默认`8766`。

**线程模型：** 在守护线程中运行`serve_forever()`。不要阻塞主线程。

### 路由的工作原理

`_setup_routes()` 方法从`transport/registry.py` 中读取规范路由规范。 flow YAML 的 `transport.http.routes` 是最优先的，缺少的端点由兼容的后备规范和组件路由规范进行补充。模式中的`{param}` 转换为正则表达式`(?P<param>[^/]+)` 并保留为已编译的正则表达式。

当请求到达时，`_match_route(method, path)` 按顺序扫描所有路由，并使用匹配的方法和路径调用第一个路由的处理程序。路径参数在`groupdict()`中提取并传递给每个处理程序。

在每个处理程序内，路径参数被注入到 `request_data` 字典中。例如，在`/api/chat/conversations/{id}`的情况下，它被设置为`request_data["conversation_id"] = path_params.get("id", "")`。

### HTTP 路由列表

|方法|路径|处理程序（块）|
|---|---|---|
| `POST`| `/v1/chat/completions` | `defaultspack.chat_turn`（`blocks/chat/send.py`后备）|
| `POST`| `/api/chat/conversations` | `blocks/chat/create_conversation.py` |
| `GET`| `/api/chat/conversations` | `blocks/chat/list_conversations.py` |
| `GET`| `/api/chat/conversations/{id}` | `blocks/chat/get_conversation.py` |
| `PUT`| `/api/chat/conversations/{id}` | `blocks/chat/update_conversation.py` |
| `DELETE`| `/api/chat/conversations/{id}` | `blocks/chat/delete_conversation.py` |
| `POST`| `/api/chat/conversations/{id}/messages` | `defaultspack.chat_turn`（`blocks/chat/send.py`后备）|
| `POST`| `/api/chat/conversations/{id}/stream` | `defaultspack.chat_stream_turn`（`blocks/chat/stream.py`后备）|
| `POST`| `/api/chat/conversations/{id}/export` | `blocks/chat/export_conversation.py` |
| `POST`| `/api/chat/conversations/{id}/summarize` | `blocks/chat/summarize_and_trim.py` |
| `POST`| `/api/chat/conversations/{id}/auto-trim` | `blocks/chat/auto_trim.py` |
| `POST`| `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST`| `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST`| `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST`| `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET`| `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST`| `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` |
| `GET`| `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` |
| `POST`| `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` |
| `POST`| `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| `POST`| `/api/consent/check` | `blocks/tool/consent_check.py` |
| `POST`| `/api/consent/{id}/confirm` | `blocks/tool/consent_confirm.py` |
| `PUT`| `/api/prompts/{name}` | `blocks/prompt/update.py` |
| `DELETE`| `/api/prompts/{name}` | `blocks/prompt/delete.py` |
| `POST`| `/api/prompts/convert` | `blocks/prompt/convert.py` |
| `POST`| `/api/tools/create` | `blocks/tool/create.py` |
| `PUT`| `/api/tools/{name}` | `blocks/tool/update.py` |
| `DELETE`| `/api/tools/{name}` | `blocks/tool/delete.py` |
| `GET`| `/api/tools/{name}/export` | `blocks/tool/export.py` |
| `GET`| `/api/dev/inspect` | `blocks/dev/inspect.py` |
| `GET`| `/api/dev/prompt-history` | `blocks/dev/prompt_history.py` |
| `POST`| `/api/dev/edit-prompt` | `blocks/dev/edit_prompt_live.py` |
| `POST`| `/api/dev/replay` | `blocks/dev/replay.py` |
| `GET`| `/api/health` | （内嵌：健康检查）|
| `GET`| `/api/context` | （内联：包信息+接口） |
| `GET`| `/` | （静态：`ui/shell.html`）|
| `GET`| `/static/{path}` | （静态：`ui/{path}`）|

### CORS 设置

所有响应都将具有以下标头：

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

`OPTIONS` 该请求已通过 204 无内容响应进行预检。

### 请求处理流程

1.`_RequestHandler`接收HTTP请求
2.删除路径的查询字符串部分（截断`?`）
3. 与`_match_route()`匹配路线
4. 对于 POST/PUT，将 Body 解析为 JSON
5. 使用`(request_data, path_params)`调用处理函数
6. 如果结果具有`_static`标志，则将其作为静态文件返回。
7. 否则，返回 JSON 响应（400 表示错误，200 表示成功）
8. 处理程序中的异常是 500 内部服务器错误

### 上下文构建

`_build_context()`中每个处理程序生成的上下文具有以下结构：

```python
{
    "flow_id": "transport_direct",
    "step_id": "http_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",  # ISO 8601
    "owner_pack": "defaultspack",
    "inputs": {},
}
```

### 内核外观

传递给`DefaultsHttpServer`构造函数的`facade`是内核的`io.http.server`模块提供的`KernelFacade`实例。如果默认包在没有内核的情况下独立运行，则通过`None`。如果设置了外观，则`/api/context`端点调用`facade.list_interfaces()`并返回接口信息。

---

## stdio 传输 (`transport/stdio.py`)

### 默认StdioTransport

使用 stdin/stdout 的 JSONL（JSON Lines）格式传输。用于 CLI 工具和管道集成。

**启动方法：**

```python
from transport.stdio import DefaultsStdioTransport

transport = DefaultsStdioTransport()
transport.start()  # ブロッキング（stdin を読み続ける）
```

### JSONL 协议

**请求格式（1行JSON）：**

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {"model": "openai/gpt-4o"}}
```

|领域 |必填 |类型 |描述 |
|---|---|---|---|
| `method`|可选| `string` | HTTP 方法。默认`"GET"` |
| `path`|必填 | `string` |端点路径 |
| `data`|可选| `object` |请求正文 |

**响应格式（输出一行 JSON 到 stdout）：**

```json
{"status": "ok", "data": {...}}
```

### stdio 路由列表

stdio 传输使用`transport/registry.py` 中的规范路线规范。除静态文件外，与HTTP经过相同的端点->流程/功能主线。 `_ROUTE_MAP` 和`_ID_INJECT_MAP` 是现有代码的兼容导出。

|方法|路径|块模块 | ID注入|
|---|---|---|---|
| `POST`| `/v1/chat/completions` | `defaultspack.chat_turn` | — |
| `POST`| `/api/chat/conversations` | `blocks.chat.create_conversation` | — |
| `GET`| `/api/chat/conversations` | `blocks.chat.list_conversations` | — |
| `GET`| `/api/chat/conversations/{id}` | `blocks.chat.get_conversation` | `conversation_id` ← `id` |
| `PUT`| `/api/chat/conversations/{id}` | `blocks.chat.update_conversation` | `conversation_id` ← `id` |
| `DELETE`| `/api/chat/conversations/{id}` | `blocks.chat.delete_conversation` | `conversation_id` ← `id` |
| `POST`| `/api/chat/conversations/{id}/messages` | `defaultspack.chat_turn` | `conversation_id` ← `id` |
| `POST`| `/api/chat/conversations/{id}/stream` | `defaultspack.chat_stream_turn` | `conversation_id` ← `id` |
| `POST`| `/api/chat/conversations/{id}/export` | `blocks.chat.export_conversation` | `conversation_id` ← `id` |
| `POST`| `/api/agent/execute` | `blocks.agent.execute` | — |
| `POST`| `/api/agent/{id}/approve` | `blocks.agent.approve` | `execution_id` ← `id` |
| `POST`| `/api/agent/{id}/reject` | `blocks.agent.reject` | `execution_id` ← `id` |
| `POST`| `/api/agent/{id}/cancel` | `blocks.agent.cancel` | `execution_id` ← `id` |
| `GET`| `/api/agent/{id}/status` | `blocks.agent.status` | `execution_id` ← `id` |
| `GET`| `/api/health` | （内联）| — |
| `GET`| `/api/context` | （内联）| — |

静态文件传送（`/`、`/chat`、`/static/{path}`）是 HTTP 传输所独有的。

### 路由

路由匹配由`_match_route()`函数执行。与 HTTP 传输类似，将`{param}` 转换为正则表达式并匹配。路径参数的注入是通过参考`_ID_INJECT_MAP`字典来完成的。

### 上下文构建

stdio 传输在`_build_context()`中生成的上下文：

```python
{
    "flow_id": "stdio_direct",
    "step_id": "stdio_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaultspack",
    "inputs": {},
}
```

---

## UDS 传输 (`transport/uds.py`)

### 默认UdsTransport

使用 Unix 域套接字进行传输。用于本地进程间通信。

**启动方法：**

```python
from transport.uds import DefaultsUdsTransport

transport = DefaultsUdsTransport(socket_path="/tmp/rumi_defaults.sock")
transport.start()  # ブロッキング
```

**环境变量：**

`DEFAULTS_UDS_PATH` — 套接字路径。默认`/tmp/rumi_defaults.sock`。

### 协议

长度前缀方式：4字节（big-endian）消息长度+JSON字节串。

**要求：**

```
[4 bytes: length][JSON bytes]
```

JSON的结构与stdio相同：

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {...}}
```

**回应：**

```
[4 bytes: length][JSON bytes]
```

### 消息大小限制

最大 10 MB（10 * 1024 * 1024 字节）。如果超过限制，将返回错误响应。

### 线程模型

接受循环在主线程上运行，每个客户端连接都由守护线程处理。待办事项 8，带有`listen(8)`。套接字超时为 1 秒。

### 路由

使用与 stdio 传输相同的`_ROUTE_MAP`和`_ID_INJECT_MAP`。可用路线与 stdio 传输相同。

### 上下文构建

`_build_context()` 中 UDS 传输生成的上下文：

```python
{
    "flow_id": "uds_direct",
    "step_id": "uds_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaults",
    "inputs": {},
}
```

### 生命周期

`start()` 调用`unlink`时如果存在现有套接字文件。 `stop()` 调用时也会删除套接字文件。
