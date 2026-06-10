<!-- docs-i18n-links:start -->
[EN](./concepts.md) | [JP](./i18n/ja/concepts.md) | [KR](./i18n/ko/concepts.md) | [CN](./i18n/zh-cn/concepts.md)
<!-- docs-i18n-links:end -->

# Concepts

Explains the core concepts of rumiai defaults pack.

## What is Pack?

A pack is an application unit in the rumiai ecosystem. The defaults pack is a pack that comes standard with rumiai and provides chat, agent, coding, AI client, tools, prompts, memory, media, and front end functions.

Each Pack declares its structure (components, handler list, loading order) in `ecosystem.json`. The kernel reads this file to recognize the pack and perform handler name resolution.

The pack name is used at the beginning of the handler name. All handlers in the defaults pack start with `defaults.` (e.g. `defaults.chat.send`, `defaults.agent.execute`).

## What is block/handler?

block is a group of modules under the `blocks/` directory, and each file corresponds to one handler. handler is the entry point for requests and is implemented as a `run` function with the following signature:

```python
def run(input_data: dict, context: dict) -> dict:
```

**`input_data`** is a dict of request parameters. The body of the HTTP request is parsed as JSON and the URL path parameter (for example, `conversation_id`) is also appended and passed.

**`context`** is a dict containing flow information and dependent functions. `_build_context()` of `transport/http.py` constructs a context with the following fields.

| Field | Type | Description |
|---|---|---|
| `flow_id` | `str` | Flow ID. `"transport_direct"` for direct HTTP calls |
| `step_id` | `str` | Step ID. `"http_request"` for direct HTTP calls |
| `phase` | `str` | Phase. `"execute"` |
| `ts` | `str` | ISO 8601 timestamp |
| `owner_pack` | `str` | Pack ID of the caller. `"defaults"` |
| `inputs` | `dict` | Additional input data |
| `call_handler` | `function` | Functions that call other handlers (injected via kernel) |

The **return value** can be in one of the following two formats defined in `blocks/_common.py`:

```python
# 成功
def ok(data=None):
    return {"status": "ok", "data": data}

# エラー
def error(message, code="ERROR"):
    return {"status": "error", "error": {"code": code, "message": message}}
```

## What is flow?

A flow is an execution definition that orders multiple handlers as steps. They are placed as a pair of `flow.yaml` and `handler.py` under the `flows/` directory.

### Structure of flow.yaml

```yaml
flow_id: simple_chat            # フロー ID（一意）
name: "Simple Chat"             # 表示名
description: "シンプルなチャットフロー"  # 説明
version: "1.0.0"                # バージョン
trigger:                        # トリガー定義
  type: user_input              #   トリガー種別
  config:                       #   トリガー設定
    require_conversation: true  #     会話が必要か
handler: handler.py             # フロー handler ファイル
config_schema:                  # 設定スキーマ
  model:                        #   設定キー
    type: string                #     型
    default: "stub/default"     #     デフォルト値
metadata:                       # メタデータ
  author: "defaults"
  tags: ["chat", "default"]
```

The defaults pack includes the following three flows.

- **`simple_chat`**: Simple chatflow (no tools). `config_schema` has `model` and `system_prompt_id`.
- **`agent_chat`**: Tool-enabled agent chat loop. `config_schema` has `agent_id` and `max_iterations`.
- **`planning_agent`**: Flow of task decomposition → approval → sequential execution. `config_schema` has `agent_id` and `planning_model`.

## What is domain?

domain is the business logic layer called by handler. It is placed as a subdirectory for each domain under the `domain/` directory.

The handler is a thin entry point that only does validation, calls the domain, and formats the results. The actual logic (storing data, calling AI, searching, etc.) is handled by classes in the domain layer.

The main domain classes are:

- **`domain/chat/store.py`** — `ChatStore`: In-memory CRUD for conversations and messages. Singleton.
- **`domain/agent/engine.py`** — `AgentEngine`: Agent execution loop (think → tool_call → approve → response).
- **`domain/company/message_router.py`** — `CompanySlackRuntime`: channel/thread/message/mention/task based company routing.
- **`domain/agent/multi.py`** — legacy compatibility only.
- **`domain/tool/registry.py`** — `ToolRegistry`: Registration and management of tool definitions. Singleton. Persistence to in-memory + `user_data/shared/tools/`.
- **`domain/prompt/manager.py`** — `PromptManager`: Prompt CRUD. Persistence to in-memory + `user_data/shared/prompts/`.
- **`domain/prompt/template.py`** — `PromptTemplate`: passive prompt template representation.
- **`domain/prompt/renderer.py`** — `render()`: Replace `{{variable}}` with template variable.
- **`domain/ai_client/client.py`** — `AIClient`: AI provider abstraction.

## What is transport?

Transport is a layer that accepts requests from outside and distributes them to handlers.

- **HTTP** (`transport/http.py`): `DefaultsHttpServer` starts an HTTP server using the Python standard `http.server`. Handles URL path and method routing, JSON parsing, CORS headers, and static file delivery.
- **stdio** (`transport/stdio.py`): Standard input/output transport. Used for communication via CLI and pipes.
- **UDS** (`transport/uds.py`): Unix Domain Socket transport. Used for local IPC.

## What is widget?

A widget is a Python representation of a UI component defined in `lib/rumi_widgets/`. The widget is sent from the handler to the frontend and rendered on the UI. Contains the following modules:

- `display.py` — Display widgets such as Text, CodeBlock, Image, etc.
- `controls.py` — Control widgets such as Input, Button, Select, etc.
- `layout.py` — Layout widgets such as Container, Row, Column, etc.
- `stream.py` — Stream widgets such as Stream, Indicator, etc.
- `custom.py` — Custom Widget

A handler can send a widget to the UI using `context["emit_widget"](§RUMI§0§)`.

## What is context?

context is a dict of execution context passed to handler. The main fields are:

| Field | Type | Description |
|---|---|---|
| `flow_id` | `str` | Running flow ID. `"transport_direct"` for direct call |
| `step_id` | `str` | Current step ID. `"http_request"` for direct call |
| `phase` | `str` | Execution phase. `"execute"` |
| `ts` | `str` | Timestamp (ISO 8601) |
| `owner_pack` | `str` | Caller's Pack ID |
| `inputs` | `dict` | Additional input data |
| `call_handler` | `function` | Function that calls other handlers |
| `emit_event` | `function` | Function that fires an event |
| `wait_event` | `function` | Function that waits for an event |
| `emit_widget` | `function` | Function to send Widget to UI |
| `cancel_check` | `function` | Function to check if canceled |
| `handler_config` | `dict` | Handler settings (conditions.json, etc.) |
| `session` | `dict` | Session information (session_id, workspace, etc.) |

## Relationship with InterfaceRegistry / EventBus

**InterfaceRegistry** is a registry of interfaces managed by the kernel. The interface (handler) provided by each Pack is registered and used for name resolution by `call_handler`. You can get a list of registered interfaces by calling `facade.list_interfaces()` on the `/api/context` endpoint.

**EventBus** is a kernel-managed event bus. You can fire an event with `context["emit_event"](§RUMI§0§)` and wait for an event with `context["wait_event"](§RUMI§1§)`. Used for asynchronous communication between handlers and flows.
