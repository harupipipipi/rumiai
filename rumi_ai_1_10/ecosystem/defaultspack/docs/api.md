<!-- docs-i18n-links:start -->
[EN](./api.md) | [JP](./i18n/ja/api.md) | [KR](./i18n/ko/api.md) | [CN](./i18n/zh-cn/api.md)
<!-- docs-i18n-links:end -->

# api.md — Rumi AI OS API & Transport design document

## 1. Overview

Defaults provides a "mechanism" to accept communications from outside. Specific endpoints (chat, model list, etc.) are registered by Flow's api trigger. The defaults only define the basics of routing, authentication, streaming, and error formats, and what can be done is determined by the Flow definition on the user_data side.

Tauri frontend, CLI, external scripts, webhooks, all reach the same Flow. The only difference is the transport (how the message is carried).


## 2. Design philosophy

**Transport independent**: All communication ultimately results in a call to `FlowEngine.execute(flow_id, trigger_input)`. Whether via HTTP, stdin/stdout, or UDS, trigger_input that reaches Flow has the same format.**Endpoints are flows**: HTTP's `/v1/chat/completions` and CLI's `rumi chat` both launch the same `default.chat` flow. Adding an endpoint is an addition to the Flow definition and does not involve changing the code.**Authentication is done at the transport layer**: API key for HTTP, parent process trust for stdio, socket permissions for UDS. The Flow layer only accepts authenticated requests.**Streaming is absorbed by transport**: Flow only issues events in `ctx.emit()`. HTTP transport is converted to SSE, stdio transport is converted to JSON Lines, and Tauri transport is converted to IPC Channel. Flow does not know which transport it will be delivered on.


## 3. Architecture

```
外部            transport 層               Flow Engine
───────────    ───────────────────        ─────────────
HTTP Client ─→ http transport ─┐
                               ├──→ router ──→ FlowEngine.execute()
CLI         ─→ stdio transport ┤                    ↓
                               │              Flow handler.py
Tauri       ─→ stdin/stdout ───┤                    ↓
                               │              ctx.emit() ──→ transport が配信
UDS Client  ─→ uds transport ──┘
```

The transport layer is implemented as a defaults handler.

| handler | transport | permissions |
|---|---|---|
| `defaults.transport.http` | HTTP Server | `frontend.serve`, `frontend.bind` |
| `defaults.transport.stdio` | Standard input/output | `frontend.serve` |
| `defaults.transport.uds` | Unix Domain Socket | `frontend.serve`, `frontend.bind` |

Each transport handler operates only with the privileges granted by the grant, and does not access the entire kernel object (avoiding the io.http.server issue).


## 4. Common message format

JSON format common to all transports. Transport either passes this format as is or converts it to its own protocol.

### 4.1 Request

```json
{
  "id": "req_01JXYZ",
  "flow_id": "default.chat",
  "input": {
    "model": "anthropic/claude-sonnet-4",
    "messages": [
      {"role": "user", "content": "hello"}
    ],
    "stream": true
  },
  "config": {}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| id | string | optional | request identifier. Automatically generated if omitted |
| flow_id | string | Required | ID of the Flow to start |
| input | object | Required | Flow trigger_input |
| config | object | optional | flow_config override for Flow |

### 4.2 Response (non-streaming)

```json
{
  "id": "req_01JXYZ",
  "status": "completed",
  "output": {
    "content": "Hello! How can I help you?",
    "model": "claude-sonnet-4-20250514",
    "usage": {
      "input_tokens": 12,
      "output_tokens": 8,
      "total_tokens": 20
    },
    "finish_reason": "stop"
  },
  "metadata": {
    "flow_id": "default.chat",
    "duration_ms": 1200
  }
}
```

| Field | Type | Description |
|---|---|---|
| id | string | request identifier |
| status | string | `completed`, `error`, `cancelled`, `timeout` |
| output | object | Flow output (FlowResult.output) |
| metadata | object | execution metadata |

### 4.3 Response (Streaming)

During streaming, multiple events are distributed according to the transport. The format of each event is the same.

```json
{"event": "stream.start", "id": "req_01JXYZ", "data": {}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "Hello"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "!"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_start", "id": "tc_01", "name": "file_read"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_delta", "arguments_chunk": "{\"path\":"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_end", "id": "tc_01"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "thinking_delta", "content": "Let me think..."}}
{"event": "stream.end", "id": "req_01JXYZ", "data": {"status": "completed", "output": {...}, "metadata": {...}}}
```

`data.type` of stream.delta is the same as the normalized event list in ai_client.md section 11.3. The transport layer converts this event sequence into a protocol-specific format.

### 4.4 Error

```json
{
  "id": "req_01JXYZ",
  "status": "error",
  "error": {
    "type": "flow_not_found",
    "message": "Flow 'nonexistent' is not registered",
    "code": "FLOW_NOT_FOUND",
    "details": {}
  }
}
```

Error code system.

| Code | Description |
|---|---|
| `AUTH_REQUIRED` | Authentication required |
| `AUTH_INVALID` | API key is invalid |
| `FLOW_NOT_FOUND` | Specified flow_id does not exist |
| `FLOW_ERROR` | Error while running Flow |
| `FLOW_TIMEOUT` | Flow timed out |
| `FLOW_CANCELLED` | Cancelled by user or system |
| `VALIDATION_ERROR` | Invalid input format |
| `PERMISSION_DENIED` | Insufficient authority |
| `RATE_LIMITED` | Rate Limit |
| `INTERNAL_ERROR` | Internal error |


## 5. HTTP Transport

### 5.1 Startup

`defaults.transport.http` handler starts the HTTP server. Settings are done in user_data.

```json
// user_data/config/transport.json
{
  "http": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 3000,
    "cors": {
      "enabled": false,
      "origins": []
    }
  }
}
```

### 5.2 Authentication

HTTP transport performs authentication for each request.

```
Authorization: Bearer rumi_xxxxxxxxxxxx
```

API keys are managed in `user_data/secrets/api_keys.json`.

```json
{
  "keys": [
    {
      "id": "key_01",
      "key_hash": "sha256:abc...",
      "name": "My API Key",
      "created_at": "2026-02-14T10:00:00Z",
      "permissions": ["*"],
      "rate_limit": {
        "requests_per_minute": 60
      }
    }
  ]
}
```

`permissions` is a Flow level permission. `["*"]` can access all Flows. It can be restricted as in `["default.chat", "default.model_list"]`.

### 5.3 Routing

Mapping from HTTP endpoint to flow_id is defined in `user_data/config/routes.json`.

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools"
      },
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "description": "モデル一覧"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    }
  ]
}
```

`input_mapping` is a field mapping from HTTP request to common message format `input`. `body.model` means the `model` field of the request body. `"*": "body"` makes the entire body an input. `{flow_id}` is a path parameter.

You can add any HTTP endpoint just by editing routes.json. No code changes required on the Flow side. Packs can also add entries to routes.json.

### 5.4 Request processing flow

```
HTTP リクエスト受信
  ↓
認証（Authorization ヘッダー → api_keys.json 照合）
  → 失敗: 401 AUTH_REQUIRED / AUTH_INVALID
  ↓
ルーティング（method + path → routes.json 照合）
  → 失敗: 404 FLOW_NOT_FOUND
  ↓
input_mapping でリクエストボディを共通形式に変換
  ↓
APIキーの permissions で flow_id へのアクセス権を確認
  → 失敗: 403 PERMISSION_DENIED
  ↓
レート制限チェック
  → 超過: 429 RATE_LIMITED
  ↓
FlowEngine.execute(flow_id, input)
  ↓
stream == false:
  → Flow 完了まで待機 → JSON レスポンス返却
  → Content-Type: application/json

stream == true:
  → SSE ストリーム開始
  → Content-Type: text/event-stream
  → Flow の ctx.emit() イベントを SSE イベントに変換して逐次送信
  → Flow 完了時に stream.end を送信して接続を閉じる
```

### 5.5 SSE Streaming

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: stream.start
data: {"id":"req_01JXYZ","data":{}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"Hello"}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"!"}}

event: stream.end
data: {"id":"req_01JXYZ","data":{"status":"completed","output":{...}}}

```

### 5.6 OpenAI Compatibility Mode

Adding `response_format: "openai"` to the `/v1/chat/completions` endpoint in routes.json converts the response to an OpenAI API compatible format and returns it.

```json
{
  "method": "POST",
  "path": "/v1/chat/completions",
  "flow_id": "default.chat",
  "input_mapping": {
    "model": "body.model",
    "messages": "body.messages",
    "stream": "body.stream",
    "temperature": "body.temperature",
    "max_tokens": "body.max_tokens",
    "tools": "body.tools"
  },
  "response_format": "openai"
}
```

The conversion is performed by the transport layer. Map Flow output (common format) to OpenAI response format.

```json
// 共通形式からの変換
{
  "id": "chatcmpl-xxxx",
  "object": "chat.completion",
  "created": 1709000000,
  "model": "claude-sonnet-4-20250514",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  }
}
```

Converts to OpenAI compatible SSE format even when streaming. This allows existing OpenAI SDKs and libraries to connect to rumi as is.

### 5.7 External Input Intake

External input routes are provider adapters, not chat runtime contracts. They
should normalize inbound provider payloads into `ExternalEvent`, evaluate
`AudiencePolicy`, select an `InputProfile`, call `submit_input`, and return or
send a response through `ResponsePlanner` plus `ResponseAdapter`.

Current defaultspack HTTP routes include:

| method | path | role |
|---|---|---|
| `GET` | `/api/integrations/secrets` | secret status only, no raw values |
| `POST` | `/api/integrations/secrets` | write-only set or clear for supported provider secrets |
| `POST` | `/api/integrations/slack/events` | Slack event intake |
| `POST` | `/api/integrations/line/webhook` | LINE webhook intake |
| `POST` | `/api/integrations/discord/interactions` | Discord interaction intake |
| `POST` | `/api/integrations/discord/events` | Discord event intake |
| `GET` | `/api/external/tokens` | masked external token status |
| `POST` | `/api/external/tokens` | write-only external token upsert, rename, delete |
| `POST` | `/api/webhooks/inbound/{webhook_id}` | generic webhook intake |
| `GET` | `/api/webhooks/endpoints` | list webhook endpoint configs |
| `POST` | `/api/webhooks/endpoints` | create webhook endpoint config |
| `PUT` | `/api/webhooks/endpoints/{webhook_id}` | update webhook endpoint config |
| `DELETE` | `/api/webhooks/endpoints/{webhook_id}` | delete webhook endpoint config |
| `POST` | `/api/webhooks/endpoints/{webhook_id}/test` | run a webhook test payload |
| `GET` | `/api/webhooks/public-urls` | list public URL providers and the local default URL |
| `POST` | `/api/webhooks/public-urls` | create a provider-backed public URL; failures return redacted `ok: false` data |
| `DELETE` | `/api/webhooks/public-urls/{url_id}` | close or clear a public URL |

Cloudflare Quick Tunnel may supply a temporary public URL for development, but
the API contract must not depend on it. The External Input UI uses it only to
generate a copyable provider webhook URL such as
`https://...trycloudflare.com/api/integrations/line/webhook`. Any tunnel or
hosted ingress should feed the same local routes.


## 6. stdio Transport

### 6.1 Overview

Send and receive JSON Lines on stdin/stdout. Communication between the Tauri frontend and the rumiai process, and the CLI, use this transport.

### 6.2 Format

stdin (client → rumiai):

```jsonl
{"id":"req_01","flow_id":"default.chat","input":{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}],"stream":false}}
{"id":"req_02","flow_id":"default.model_list","input":{}}
```

stdout (rumiai → client):

```jsonl
{"id":"req_01","status":"completed","output":{"content":"Hello!","model":"gpt-4o","usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15},"finish_reason":"stop"},"metadata":{"flow_id":"default.chat","duration_ms":800}}
{"id":"req_02","status":"completed","output":{"models":[...]},"metadata":{"flow_id":"default.model_list","duration_ms":50}}
```

When streaming:

```jsonl
{"event":"stream.start","id":"req_03","data":{}}
{"event":"stream.delta","id":"req_03","data":{"type":"content_delta","content":"Hello"}}
{"event":"stream.end","id":"req_03","data":{"status":"completed","output":{...}}}
```

### 6.3 Authentication

stdio transport does not perform authentication. Only the parent process (Tauri's Rust layer, or the shell that started the CLI) can connect to stdin/stdout, so trust between processes is sufficient.

### 6.4 Integration with front-end messages

Front-end specific messages such as `component.register`, `render.mount`, `message.send` defined in frontend.md also share the same stdin/stdout. The distinction is made by the presence or absence of the `type` field.

```jsonl
// Flow 呼び出し（type フィールドなし、flow_id フィールドあり）
{"id":"req_01","flow_id":"default.chat","input":{...}}

// フロントエンドメッセージ（type フィールドあり）
{"type":"asset.register","data":{"asset_id":"defaults.chat","entry":"ui/chat.html",...}}
{"type":"message.send","component":"defaults.chat","data":{...}}
```

A transport handler distributes messages. If `flow_id` is present, forward to FlowEngine; if `type` is present, forward to front-end handler.


## 7. UDS Transport

### 7.1 Overview

Communicate using Unix Domain Socket. Used when another local process (another application, script, editor plugin, etc.) communicates with rumiai.

### 7.2 Settings

```json
// user_data/config/transport.json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock"
  }
}
```

### 7.3 Protocol

JSON Lines. Same format as stdio transport.

### 7.4 Authentication

Controlled by socket file permissions (`0600`, only the owner can read and write). It is also possible to configure settings to additionally require API key authentication.

```json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock",
    "require_auth": true
  }
}
```

In the case of `require_auth: true`, authentication is performed in the first message after connection.

```jsonl
{"type":"auth","key":"rumi_xxxxxxxxxxxx"}
{"type":"auth.result","status":"ok"}
```


## 8. CLI integration

### 8.1 Overview

The CLI is a thin client built on top of the stdio transport. Start the rumiai process and send and receive common message formats on stdin/stdout. The CLI itself has no domain knowledge.

### 8.2 Command system

The CLI command is an alias to flow_id.

```
rumi chat "hello"
  → {"flow_id": "default.chat", "input": {"messages": [{"role": "user", "content": "hello"}], "stream": true}}

rumi models
  → {"flow_id": "default.model_list", "input": {}}

rumi run my_custom_flow --input '{"key": "value"}'
  → {"flow_id": "my_custom_flow", "input": {"key": "value"}}
```

The mapping between command and flow_id is defined in `user_data/config/cli.json`.

```json
{
  "commands": {
    "chat": {
      "flow_id": "default.chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "model": "{flags.model}",
        "stream": true
      },
      "flags": {
        "model": {"short": "m", "default": null},
        "no-stream": {"type": "bool", "default": false}
      }
    },
    "models": {
      "flow_id": "default.model_list",
      "input_template": {}
    },
    "agent": {
      "flow_id": "default.agent_chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "agent_id": "{flags.agent}",
        "stream": true
      },
      "flags": {
        "agent": {"short": "a", "default": "coding_assistant"}
      }
    }
  },
  "aliases": {
    "c": "chat",
    "m": "models",
    "a": "agent"
  }
}
```

If a Pack adds a command to cli.json, you can call that Pack's Flow from the CLI. No need to change the CLI code.

### 8.3 Output format

The CLI converts the common format responses received from the transport into a human-readable format.

Non-streaming:

```
$ rumi chat "hello" --no-stream
Hello! How can I help you today?

[gpt-4o | 20 tokens | 1.2s]
```

Streaming:

```
$ rumi chat "hello"
Hello! How can I help you today?█
```

When streaming, text chunks of stream.delta are output sequentially. The cursor appears at the end. Completed with stream.end reception.

### 8.4 Widget text fallback

If a Flow or tool sends Widget JSON with emit_widget, the CLI will fall back to the widget's text representation.

| Widget type | CLI display |
|---|---|
| Text | Output as text |
| CodeBlock | ``` Enclosure + language name |
| Diff | unified diff format |
| Image | `[Image: alt WxH]` |
| Screenshot | `[Screenshot: url]` |
| Terminal | Command and output as is |
| Progress | `[████░░░░░░] 40%` |
| Table | ASCII table |
| FileTree | Indented text |
| Markdown | Output as is |
| Chart | Numerical summary |
| Audio | `[Audio: duration]` |
| Video | `[Video: duration]` |
| Map | `[Map: lat, lng]` |
| Indicator | `● label (state)` |
| Card | Text combination of header + body |


## 9. Endpoint registration mechanism

### 9.1 Flow api triggers

The HTTP endpoint is registered in `trigger.type: api` of the Flow definition. Works with flow.md's trigger system.

```yaml
# user_data/shared/flows/my_api/flow.yaml
flow_id: my_custom_api
trigger:
  type: api
  config:
    endpoint: "/v1/my/endpoint"
    method: POST
    auth_required: true

handler: handler.py
```

When the Flow is deployed, the transport.http handler reloads the routes and this endpoint is enabled.

### 9.2 Relationship with routes.json

routes.json is a static routing definition. Flow api triggers are registered dynamically. The solution order is as follows.

1. Static routes in routes.json (highest priority)
2. Dynamic route registered with Flow api trigger

If the same path conflicts, routes.json wins.

### 9.3 Pack adds endpoints

Packs can add endpoints in two ways.

Method 1: Define an api trigger for Flow.

```yaml
# user_data/packs/my_pack/flows/webhook_receiver/flow.yaml
flow_id: my_pack.webhook
trigger:
  type: api
  config:
    endpoint: "/hooks/my_pack"
    method: POST
    auth_required: false
handler: handler.py
```

Method 2: Add an entry to routes.json (via the Pack's installation script).

Either method requires no code changes on the defaults side.


## 10. Security

### 10.1 Transport layer isolation

Each transport handler operates only with the permissions granted by Grant. The problem of passing the entire kernel object as in `io.http.server` does not occur.

### 10.2 Authentication hierarchy

| transport | Authentication method | Basis |
|---|---|---|
| HTTP | API key (Bearer token) | Access via network always requires authentication |
| stdio | None | Parent process trust |
| UDS | Socket permissions + optional API key | Local process trust + configurable |

### 10.3 Flow Level Permissions

Accessible flows can be restricted for each key using the `permissions` field of the API key. Keys with strong administrative privileges can be separated from keys for limited use.

### 10.4 Rate Limiting

Implemented in the transport layer. `requests_per_minute` can be set for each API key. If exceeded, `429 RATE_LIMITED` is returned.

### 10.5 Validation of input

Input validation according to Flow's `config_schema` (flow.md section 6.1) is performed by FlowEngine. The transport layer only performs format checking (is it valid as JSON?).


## 11. Default route

Default route that defaults registers in routes.json. All can be overwritten/deleted in user_data's routes.json.

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools",
        "tool_choice": "body.tool_choice"
      },
      "response_format": "openai",
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "response_format": "openai",
      "description": "OpenAI 互換モデル一覧"
    },
    {
      "method": "GET",
      "path": "/v1/models/{model_id}",
      "flow_id": "default.model_info",
      "input_mapping": {
        "model_id": "path.model_id"
      },
      "response_format": "openai",
      "description": "OpenAI 互換モデル情報"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    },
    {
      "method": "GET",
      "path": "/v1/flows",
      "flow_id": "default.flow_list",
      "input_mapping": {},
      "description": "登録済み Flow の一覧"
    },
    {
      "method": "GET",
      "path": "/health",
      "flow_id": "default.health",
      "input_mapping": {},
      "description": "ヘルスチェック"
    }
  ]
}
```

### 11.1 Notation of input_mapping

| Notation | Explanation | Example |
|---|---|---|
| `body.{field}` | Request body fields | `body.model` |
| `path.{param}` | URL path parameters | `path.model_id` |
| `query.{param}` | Query parameters | `query.limit` |
| `header.{name}` | Request header | `header.X-Custom` |
| `"*": "body"` | Make the entire body input | — |

### 11.2 response_format

| Value | Description |
|---|---|
| Omitted / `"default"` | Return as is in common message format |
| `"openai"` | Convert and return to OpenAI API compatible format |

`"anthropic"` etc. can be added in the future. Place the conversion logic in the transport layer.


## 12. Relationship with other documents

| Document | Relationship |
|---|---|
| frontend.md | The message format of the stdio transport coexists with the communication flow of frontend.md. If you have `flow_id`, go to FlowEngine, if you have `type`, go to front end |
| flow.md | Endpoints are registered with Flow's api trigger. FlowEngine processes the request |
| ai_client.md | Streaming event type is the same as normalized event in ai_client.md section 11.3 |
| tool.md | Transport is not manipulated using the tool's context API (call_handler, emit_event, etc.). transport is an upper layer and is not touched directly by tools |
| external-inputs.md | Defines the provider-neutral intake path: `ExternalEvent`, `AudiencePolicy`, `InputProfile`, `submit_input`, `ResponsePlanner`, and `ResponseAdapter` |
| webhooks.md | Documents webhook-specific verification and ack behavior before normalized submission |
