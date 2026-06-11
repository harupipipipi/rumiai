<!-- docs-i18n-links:start -->
[EN](./transport.md) | [JP](./i18n/ja/transport.md) | [KR](./i18n/ko/transport.md) | [CN](./i18n/zh-cn/transport.md)
<!-- docs-i18n-links:end -->

# Transport layer

Defaults Pack provides three types of transport as a means of communication with front ends and clients. Both are located in the `transport/` directory.

---

## Overview

The transport layer is an intermediate layer that receives requests from clients, calls the corresponding block's `run(input_data, context)` function, and returns a response. All transports call the same block, but differ in the range of available routes. The HTTP transport provides the most routes, and the stdio/UDS transport only provides a subset of core routes.

Transport selection is determined at startup. `defaults.frontend.start` handler launches the appropriate transport based on the `transport` parameters.

---

## HTTP server (`transport/http.py`)

### DefaultsHttpServer

`DefaultsHttpServer` is an HTTP server based on `http.server.HTTPServer` of the Python standard library.

```python
from transport.http import start_http_server

server = start_http_server(facade)  # KernelFacade or None
```

**Constructor arguments:**

`facade` — KernelFacade instance of the kernel. `/api/context` Used to call `list_interfaces()` on the endpoint. None is also possible.

**Environment variables:**

`DEFAULTS_HTTP_HOST` — Bind host. Default `127.0.0.1`.
`DEFAULTS_HTTP_PORT` — Bind port. Default `8766`.

**Threading model:** Run `serve_forever()` in a daemon thread. Don't block the main thread.

### How routing works

Define all routes as `(method, pattern, handler)` tuples using the `_setup_routes()` method. `{param}` in the pattern is converted to regular expression `(?P<param>[^/]+)` and kept as a compiled regular expression.

When a request arrives, `_match_route(method, path)` scans all routes in order and calls the handler for the first route with a matching method and path. Path parameters are extracted in `groupdict()` and passed to each handler.

Inside each handler, path parameters are injected into a `request_data` dict. For example, in the case of `/api/chat/conversations/{id}`, it is set as `request_data["conversation_id"] = path_params.get("id", "")`.

### HTTP route list

| method | path | handler (block) |
|---|---|---|
| `POST` | `/v1/chat/completions` | `blocks/chat/send.py` |
| `POST` | `/api/chat/conversations` | `blocks/chat/create_conversation.py` |
| `GET` | `/api/chat/conversations` | `blocks/chat/list_conversations.py` |
| `GET` | `/api/chat/conversations/{id}` | `blocks/chat/get_conversation.py` |
| `PUT` | `/api/chat/conversations/{id}` | `blocks/chat/update_conversation.py` |
| `DELETE` | `/api/chat/conversations/{id}` | `blocks/chat/delete_conversation.py` |
| `POST` | `/api/chat/conversations/{id}/messages` | `blocks/chat/send.py` |
| `POST` | `/api/chat/conversations/{id}/stream` | `blocks/chat/stream.py` |
| `POST` | `/api/chat/conversations/{id}/export` | `blocks/chat/export_conversation.py` |
| `POST` | `/api/chat/conversations/{id}/summarize` | `blocks/chat/summarize_and_trim.py` |
| `POST` | `/api/chat/conversations/{id}/auto-trim` | `blocks/chat/auto_trim.py` |
| `POST` | `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST` | `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST` | `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST` | `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET` | `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` |
| `POST` | `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| `POST` | `/api/consent/check` | `blocks/tool/consent_check.py` |
| `POST` | `/api/consent/{id}/confirm` | `blocks/tool/consent_confirm.py` |
| `PUT` | `/api/prompts/{name}` | `blocks/prompt/update.py` |
| `DELETE` | `/api/prompts/{name}` | `blocks/prompt/delete.py` |
| `POST` | `/api/prompts/convert` | `blocks/prompt/convert.py` |
| `POST` | `/api/tools/create` | `blocks/tool/create.py` |
| `PUT` | `/api/tools/{name}` | `blocks/tool/update.py` |
| `DELETE` | `/api/tools/{name}` | `blocks/tool/delete.py` |
| `GET` | `/api/tools/{name}/export` | `blocks/tool/export.py` |
| `GET` | `/api/dev/inspect` | `blocks/dev/inspect.py` |
| `GET` | `/api/dev/prompt-history` | `blocks/dev/prompt_history.py` |
| `POST` | `/api/dev/edit-prompt` | `blocks/dev/edit_prompt_live.py` |
| `POST` | `/api/dev/replay` | `blocks/dev/replay.py` |
| `GET` | `/api/health` | (Inline: Health Check) |
| `GET` | `/api/context` | (Inline: Pack information + interfaces) |
| `GET` | `/` | (Static: `ui/shell.html`) |
| `GET` | `/static/{path}` | (Static: `ui/{path}`) |

### CORS settings

All responses will have the following headers:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

`OPTIONS` The request is preflighted with a 204 No Content response.

### Request processing flow

1. `_RequestHandler` receives an HTTP request
2. Remove the query string part of the path (cut off `?`)
3. Matching routes with `_match_route()`
4. For POST/PUT, parse the Body as JSON
5. Call the handler function with `(request_data, path_params)`
6. If the result has the `_static` flag, return it as a static file.
7. Otherwise, return as JSON response (400 for error, 200 for success)
8. Exception in handler is 500 Internal Server Error

### Context construction

The context generated by each handler in `_build_context()` has the following structure:

```python
{
    "flow_id": "transport_direct",
    "step_id": "http_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",  # ISO 8601
    "owner_pack": "defaults",
    "inputs": {},
}
```

### KernelFacade

The `facade` passed to the constructor of `DefaultsHttpServer` is a `KernelFacade` instance provided by the kernel's `io.http.server` module. Pass `None` if the defaults pack runs standalone without a kernel. If facade is set, the `/api/context` endpoint calls `facade.list_interfaces()` and returns interface information.

---

## stdio transport (`transport/stdio.py`)

### DefaultsStdioTransport

JSONL (JSON Lines) format transport using stdin/stdout. For CLI tools and pipeline integrations.

**Startup method:**

```python
from transport.stdio import DefaultsStdioTransport

transport = DefaultsStdioTransport()
transport.start()  # ブロッキング（stdin を読み続ける）
```

### JSONL Protocol

**Request format (1 line JSON):**

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {"model": "openai/gpt-4o"}}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `method` | Optional | `string` | HTTP method. Default `"GET"` |
| `path` | Required | `string` | Endpoint path |
| `data` | Optional | `object` | Request body |

**Response format (outputs one line of JSON to stdout):**

```json
{"status": "ok", "data": {...}}
```

### stdio route list

The stdio transport provides a subset of the HTTP transport. All routes defined in `_ROUTE_MAP` of `transport/stdio.py` are as follows:

| Method | Path | block module | ID injection |
|---|---|---|---|
| `POST` | `/v1/chat/completions` | `blocks.chat.send` | — |
| `POST` | `/api/chat/conversations` | `blocks.chat.create_conversation` | — |
| `GET` | `/api/chat/conversations` | `blocks.chat.list_conversations` | — |
| `GET` | `/api/chat/conversations/{id}` | `blocks.chat.get_conversation` | `conversation_id` ← `id` |
| `PUT` | `/api/chat/conversations/{id}` | `blocks.chat.update_conversation` | `conversation_id` ← `id` |
| `DELETE` | `/api/chat/conversations/{id}` | `blocks.chat.delete_conversation` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/messages` | `blocks.chat.send` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/stream` | `blocks.chat.stream` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/export` | `blocks.chat.export_conversation` | `conversation_id` ← `id` |
| `POST` | `/api/agent/execute` | `blocks.agent.execute` | — |
| `POST` | `/api/agent/{id}/approve` | `blocks.agent.approve` | `execution_id` ← `id` |
| `POST` | `/api/agent/{id}/reject` | `blocks.agent.reject` | `execution_id` ← `id` |
| `POST` | `/api/agent/{id}/cancel` | `blocks.agent.cancel` | `execution_id` ← `id` |
| `GET` | `/api/agent/{id}/status` | `blocks.agent.status` | `execution_id` ← `id` |
| `GET` | `/api/health` | (inline) | — |
| `GET` | `/api/context` | (inline) | — |

**Total: 16 routes** (14 handler modules + 2 inline systems)

### Routes that exist only in HTTP (not in stdio)

The following routes are only available on the HTTP transport and are not included on the stdio transport:

- `POST /api/chat/conversations/{id}/summarize` — Summary/trim
- `POST /api/chat/conversations/{id}/auto-trim` — automatic trim
- `POST /api/agent/multi/execute` — Multi-agent execution
- `GET /api/agent/multi/{id}/status` — Multi-agent status
- `POST /api/agent/multi/{id}/message` — Multi-agent messages
- `POST /api/agent/{id}/instruct` — Agent instructions added
- `POST /api/consent/check` — Consent check
- `POST /api/consent/{id}/confirm` — Consent confirmation
- `PUT /api/prompts/{name}` — prompt update
- `DELETE /api/prompts/{name}` — Prompt removed
- `POST /api/prompts/convert` — prompt ↔ tool conversion
- `POST /api/tools/create` — Tool creation
- `PUT /api/tools/{name}` — Tool update
- `DELETE /api/tools/{name}` — Tool deletion
- `GET /api/tools/{name}/export` — Tool export
- `GET /api/dev/inspect` — Dev: inspect
- `GET /api/dev/prompt-history` — Dev: Prompt history
- `POST /api/dev/edit-prompt` — Dev: Edit prompt
- `POST /api/dev/replay` — Dev: Replay
- `GET /` — Static file (shell.html)
- `GET /static/{path}` — Static file distribution

### Routing

Route matching is performed by the `_match_route()` function. Similar to HTTP transport, convert `{param}` into a regular expression and match. Injection of path parameters is done by referring to `_ID_INJECT_MAP` dict.

### Context construction

The context that stdio transport generates in `_build_context()`:

```python
{
    "flow_id": "stdio_direct",
    "step_id": "stdio_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaults",
    "inputs": {},
}
```

---

## UDS transport (`transport/uds.py`)

### DefaultsUdsTransport

transport using Unix Domain Sockets. For local interprocess communication.

**Startup method:**

```python
from transport.uds import DefaultsUdsTransport

transport = DefaultsUdsTransport(socket_path="/tmp/rumi_defaults.sock")
transport.start()  # ブロッキング
```

**Environment variables:**

`DEFAULTS_UDS_PATH` — Socket path. Default `/tmp/rumi_defaults.sock`.

### Protocol

Length-prefix method: 4-byte (big-endian) message length + JSON byte string.

**Request:**

```
[4 bytes: length][JSON bytes]
```

The structure of JSON is the same as stdio:

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {...}}
```

**Response:**

```
[4 bytes: length][JSON bytes]
```

### Message size limit

Maximum 10 MB (10 * 1024 * 1024 bytes). If it exceeds the limit, an error response will be returned.

### Threading model

The accept loop runs on the main thread, and each client connection is handled by a daemon thread. Backlog 8 with `listen(8)`. Socket timeout is 1 second.

### Routing

Uses the same `_ROUTE_MAP` and `_ID_INJECT_MAP` as stdio transport. Available routes are the same as stdio transport.

### Context construction

Context generated by UDS transport in `_build_context()`:

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

### Life cycle

`start()` If there is an existing socket file when calling `unlink`. `stop()` Also deletes the socket file when called.
