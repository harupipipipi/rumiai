<!-- docs-i18n-links:start -->
[EN](./dev-tools.md) | [JP](./i18n/ja/dev-tools.md) | [KR](./i18n/ko/dev-tools.md) | [CN](./i18n/zh-cn/dev-tools.md)
<!-- docs-i18n-links:end -->

# Dev Tools Guide

## 1. Concept

Dev Tools is a group of inspection and debugging functions for developers provided by defaults. Provides AI request details, prompt usage history, live editing, and request replay.

The Dev Tools handler is placed in the `blocks/dev/` directory and declared as the `dev` component of `ecosystem.json`. The specific UI panel is provided as an Asset on the user_data side, but the defaults pack includes a reference implementation in `ui/dev_panel.js`.

`blocks/dev/` contains the following files.

| file | handler name |
|---|---|
| `inspect.py` | `defaults.dev.inspect` |
| `prompt_history.py` | `defaults.dev.prompt_history` |
| `edit_prompt_live.py` | `defaults.dev.edit_prompt_live` |
| `replay.py` | `defaults.dev.replay` |


## 2. inspect (confirm request information)

View complete details of requests submitted to LLM.

**handler**: `defaults.dev.inspect`（`blocks/dev/inspect.py`）**HTTP**: `GET /api/dev/inspect`

```python
# handler 経由で直前のリクエスト情報を取得
info = context["call_handler"]("defaults.dev.inspect", {
    "conversation_id": "conv-1",
    "message_id": "msg-latest"
})
```

Return value:
```json
{
  "request": {
    "model": "claude-sonnet-4-20250514",
    "provider": "anthropic",
    "messages": [ "...StandardMessage 配列..." ],
    "tools": [ "...ツール定義..." ],
    "params": { "temperature": 0.7, "max_tokens": 8192 },
    "system_prompt": "...レンダリング済みシステムプロンプト...",
    "total_input_tokens": 12500
  },
  "response": {
    "content": [ "...Content Block 配列..." ],
    "finish_reason": "tool_calls",
    "usage": { "input_tokens": 12500, "output_tokens": 350 },
    "latency_ms": 2800,
    "time_to_first_token_ms": 650
  },
  "context_breakdown": {
    "system_prompt_tokens": 1500,
    "project_memory_tokens": 800,
    "user_memory_tokens": 200,
    "tools_tokens": 3000,
    "history_tokens": 7000,
    "reserve_tokens": 0
  }
}
```


## 3. prompt history

See the history of prompts rendered during a session.

**handler**: `defaults.dev.prompt_history`（`blocks/dev/prompt_history.py`）**HTTP**: `GET /api/dev/prompt-history`

```python
history = context["call_handler"]("defaults.dev.prompt_history", {
    "session_id": "sess-123",
    "limit": 20
})
```

Return value:
```json
[
  {
    "timestamp": 1771056800000,
    "prompt_id": "coding_system",
    "variables_used": ["agent_name", "tools", "project_memory"],
    "rendered_length": 3200,
    "source": "user_data/shared/prompts/coding_system"
  }
]
```


## 4. edit prompt live

Edit and override prompts on the fly. If the specified `prompt_name` prompt exists, `content` is updated; if it does not exist, a new one is created. Specifying `"system"` for `prompt_name` rewrites the system prompt.

**handler**: `defaults.dev.edit_prompt_live`（`blocks/dev/edit_prompt_live.py`）**HTTP**: `POST /api/dev/edit-prompt`

```python
context["call_handler"]("defaults.dev.edit_prompt_live", {
    "prompt_name": "coding_system",
    "new_body": "あなたは関数型プログラミングの専門家です。..."
})
```

Return value:
```json
{
  "status": "ok",
  "data": {
    "prompt_name": "coding_system",
    "updated": true,
    "content": "あなたは関数型プログラミングの専門家です。...",
    "prompt_id": "a1b2c3d4"
  }
}
```

To restore, specify the original template body in `new_body` and call it again.


## 5. replay (replaying past requests)

Rerun a previous LLM request with the same parameters. It is also possible to change the model and parameters.

**handler**: `defaults.dev.replay`（`blocks/dev/replay.py`）**HTTP**: `POST /api/dev/replay`

```python
result = context["call_handler"]("defaults.dev.replay", {
    "conversation_id": "conv-1",
    "message_id": "msg-005",
    "override": {
        "model": "openai/gpt-4o",
        "params": {"temperature": 0.0}
    }
})
```

The return value has the same format as `defaults.ai.complete`. Reuse the message array and tool definition from the original request, replace only the model and parameters, and rerun.


## 6. Display panel with Ctrl+Shift+D

Asset on the front end detects the `Ctrl+Shift+D` keybind and toggles the display/hide of the Dev Tools panel.

Panel Asset is provided as a pack of user_data. defaults provides Dev Tools handlers (`defaults.dev.inspect`, `defaults.dev.prompt_history`, `defaults.dev.edit_prompt_live`, `defaults.dev.replay`). A reference implementation is included in `ui/dev_panel.js` of the defaults pack.

`panel.bottom` or `floating` is recommended for the panel Asset placement slot.


## 7. API endpoints

| handler | HTTP route | input_data | return value |
|---|---|---|---|
| `defaults.dev.inspect` | `GET /api/dev/inspect` | `{conversation_id, message_id}` | Request/Response Details |
| `defaults.dev.prompt_history` | `GET /api/dev/prompt-history` | `{session_id, limit}` | Prompt usage history array |
| `defaults.dev.edit_prompt_live` | `POST /api/dev/edit-prompt` | `{prompt_name, new_body}` | `{prompt_name, updated, content, prompt_id}` |
| `defaults.dev.replay` | `POST /api/dev/replay` | `{conversation_id, message_id, override}` | StandardResponse |
