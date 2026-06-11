<!-- docs-i18n-links:start -->
[EN](./getting-started.md) | [JP](./i18n/ja/getting-started.md) | [KR](./i18n/ko/getting-started.md) | [CN](./i18n/zh-cn/getting-started.md)
<!-- docs-i18n-links:end -->

# Getting Started

A guide from setting up rumiai defaults pack to sending your first conversation.

## Prerequisites

- **Python 3.11 or higher** installed
- **rumiai kernel** has been set up (under `rumi_ai_1_10/` of `https://github.com/harupipipipi/rumiai`)
- **git** is installed

## Installation

### 1. Clone defaults pack

```bash
git clone https://github.com/harupipipipi/rumiai_defaults.git
```

### 2. Registration to the kernel

Set the defaults Pack path to the Pack registration directory of the rumiai kernel. Specify the root path of the defaults pack in the kernel's `ecosystem/` directory or configuration file. The root of the defaults Pack contains `ecosystem.json`, which the kernel reads to recognize the Pack.

```
ecosystem.json   ← カーネルが読み取る Pack 構造定義
blocks/          ← handler（ビジネスロジックの入口）
domain/          ← ドメインロジック
transport/       ← HTTP / stdio / UDS サーバー
flows/           ← Flow 定義
ui/              ← フロントエンド（shell.html, dev_panel.js）
```

### 3. Setting environment variables

The HTTP server in the defaults pack references the following environment variables. Read in `DefaultsHttpServer.__init__` of `transport/http.py`.

| Environment variables | Default value | Description |
|---|---|---|
| `DEFAULTS_HTTP_HOST` | `127.0.0.1` | HTTP server bind address |
| `DEFAULTS_HTTP_PORT` | `8766` | HTTP server port number |

If you use AI providers, also set the API key for each provider (for example, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.). If the API key is not set, the AI ​​call returns a stub response (`[stub] AI response placeholder`).

```bash
export DEFAULTS_HTTP_HOST=127.0.0.1
export DEFAULTS_HTTP_PORT=8766
export OPENAI_API_KEY=sk-...
```

## How to start

The defaults pack is launched from the kernel. When the kernel calls `defaults.frontend.start` handler, `run()` of `blocks/frontend/start.py` is executed. `run()` gets `facade` from `input_data` and calls `transport.http.start_http_server(facade)` to start the HTTP server. Returns an error if `facade` is `None`.

```python
# blocks/frontend/start.py の動作概要
def run(input_data, context):
    from transport.http import start_http_server
    facade = input_data.get("facade")
    if facade is None:
        return error("facade is required")
    server = start_http_server(facade)
    return ok({
        "message": "HTTP server started",
        "host": server.host,
        "port": server.port,
    })
```

If the startup is successful, the following message will be displayed on the console.

```
[defaults] HTTP server started on 127.0.0.1:8766
```

## Steps to send your first conversation

### Open in browser

Accessing `http://127.0.0.1:8766/` in a browser returns `ui/shell.html`. If the UI is displayed, startup is successful.

The HTTP server root `/` is processed by `_handle_static()` in `transport/http.py`, which reads and returns the path `ui/shell.html` relative to the Pack root. Additional static files (CSS, JS, images, etc.) can be accessed in `/static/{path}`, and `_handle_static_file()` loads the files from `ui/{path}`. For example, `/static/dev_panel.js` returns `ui/dev_panel.js`.

### Create a conversation and send a message with curl

#### 1. Create a conversation

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"model": "stub/default"}'
```

Response (`blocks/chat/create_conversation.py` → `create_conversation()` of `domain/chat/store.py`):

```json
{
  "status": "ok",
  "data": {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "title": "New Conversation",
    "model": "stub/default",
    "messages": [],
    "current_node_id": null,
    "tags": [],
    "is_starred": false,
    "is_archived": false,
    "created_at": 1700000000000,
    "updated_at": 1700000000000
  }
}
```

#### 2. Send a message

Use the returned `id` as `{conversation_id}`.

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations/{conversation_id}/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "content": "Hello, world!"
    }
  }'
```

This request calls `run()` of `blocks/chat/send.py`. Save user messages, send conversation history to AI, and save and return AI responses as assistant messages.

```json
{
  "status": "ok",
  "data": {
    "id": "...",
    "role": "assistant",
    "content": [{"type": "text", "text": "[stub] AI response placeholder"}],
    "conversation_id": "...",
    "parent_id": "...",
    "sequence_number": 2,
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
  }
}
```

## Troubleshooting

### Server does not start

- Please check if `DEFAULTS_HTTP_PORT` is being used by another process.
- If `input_data` does not contain `facade`, `blocks/frontend/start.py` returns `error("facade is required")`. Please check if the facade is passed correctly from the kernel.

### `[stub] AI response placeholder` is returned

- A stub response is returned if the AI provider's API key is not set or `call_handler` is `None`.
- `_stub_response()` of `blocks/chat/send.py` is used as a fallback.
- To get real AI responses, set your API key in environment variables and specify a valid model name (e.g. `openai/gpt-4o`) in `model` of the conversation.

### Conversation not found (NOT_FOUND)

- `ChatStore` is an in-memory singleton (`domain/chat/store.py`). If you restart the server, all conversation data will be lost.
- Please check if the `id` returned by conversation creation is correct.

### CORS errors

- The HTTP server allows access from all origins (`Access-Control-Allow-Origin: *`). If CORS is an issue, check the impact of browser extensions and proxies.

### Health check

You can check the server operating status below.

```bash
curl http://127.0.0.1:8766/api/health
```

```json
{
  "status": "ok",
  "data": {
    "status": "healthy",
    "pack": "defaults",
    "ts": "2025-01-01T00:00:00Z"
  }
}
```
