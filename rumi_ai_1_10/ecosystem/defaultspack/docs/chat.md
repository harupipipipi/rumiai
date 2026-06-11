<!-- docs-i18n-links:start -->
[EN](./chat.md) | [JP](./i18n/ja/chat.md) | [KR](./i18n/ko/chat.md) | [CN](./i18n/zh-cn/chat.md)
<!-- docs-i18n-links:end -->

# Chat API

A complete API reference for the defaults pack's chat functionality. The handler is implemented in `blocks/chat/` and the domain logic is implemented in `domain/chat/store.py` (ChatStore).

The chat component in ecosystem.json provides 18 handlers: `create_conversation`, `get_conversation`, `list_conversations`, `update_conversation`, `delete_conversation`, `export_conversation`, `send`, `stream`, `add_message`, `get_message`, `update_message`, `delete_message`, `branch`, `search`, `stop`, `regenerate`, `summarize_and_trim`, `auto_trim`.

## Provider-Agnostic Chat Pipeline

ChatStore remains the provider-agnostic source of truth. Stored Rumi messages are
converted to Rumi Chat IR v2 before provider planning. The legacy
`convert_to_standard()` API remains callable and still returns the historical
StandardMessage list used by existing provider adapters.

The runtime flow is:

```text
ChatStore messages
  -> Rumi Chat IR v2
  -> Provider Capability Registry
  -> Request Planner / degradation metadata
  -> legacy StandardMessage or Provider Compiler v2
  -> provider response parser
  -> assistant RumiMessage
```

`PreparedChatRun` now carries `chat_ir`, `ir_schema_version`,
`provider_capabilities`, and `provider_planning` alongside existing
`standard_messages`. Assistant metadata records the IR version, model routing,
chat references, planning warnings, dropped features, and provider trace info.

Rollback flags:

- `RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`: force the legacy
  StandardMessage provider path.
- `RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1`: opt into Provider Compiler v2 for
  supported complete calls.

Provider trace artifacts are written under
`user_data/shared/chat/conversations/<conversation_id>/workspace/provider_traces/`.
They include redacted capability, planning, payload, and response summaries.

## External input conversations

External providers should not call chat internals with raw provider payloads.
Webhook and gateway intake should first produce an `ExternalEvent`, pass
`AudiencePolicy`, select an `InputProfile`, and call `submit_input`. The chat
layer then receives a normal user message with external metadata attached.

External conversations should use `conversation_kind: "external"` and stable
session keys such as `slack:{team_id}:{channel_id}:{thread_id}` or
`line:{source_type}:{source_id}`. Replies should be planned by
`ResponsePlanner` and delivered by a `ResponseAdapter`; chat handlers should not
hold raw provider tokens or construct provider API calls directly.

## Create a conversation

**handler**: `defaults.chat.create_conversation`（`blocks/chat/create_conversation.py`）**HTTP**: `POST /api/chat/conversations`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | `string` | No | AI model name. Default `"stub/default"` |
| `system_prompt_id` | `string` | No | System Prompt ID |
| `agent_id` | `string` | No | Agent ID |
| `tags` | `string[]` | No | Tag array. Default `[]` |

**Return value** (`ok(conv)`):

```json
{
  "status": "ok",
  "data": {
    "id": "uuid",
    "title": "New Conversation",
    "created_at": 1700000000000,
    "updated_at": 1700000000000,
    "model": "stub/default",
    "system_prompt_id": null,
    "agent_id": null,
    "tags": [],
    "is_starred": false,
    "is_archived": false,
    "current_node_id": null,
    "messages": []
  }
}
```

## Get conversation

**handler**: `defaults.chat.get_conversation`（`blocks/chat/get_conversation.py`）**HTTP**: `GET /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |

**Return value**: `ok(conv)` — The entire conversation object (including messages). If not found, `error("Conversation not found", "NOT_FOUND")`.

## List of conversations

**handler**: `defaults.chat.list_conversations`（`blocks/chat/list_conversations.py`）**HTTP**: `GET /api/chat/conversations`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `limit` | `int` | No | Number of acquisitions. Default `50` |
| `offset` | `int` | No | Offset. Default `0` |
| `tag` | `string` | No | Filter by tag |
| `is_starred` | `bool` | No | Filter by star status |
| `is_archived` | `bool` | No | Filter by archive status |

**Return value**: `ok({"conversations": [...], "total": int})`. `updated_at` Sorted in descending order.

## Update conversation

**handler**: `defaults.chat.update_conversation`（`blocks/chat/update_conversation.py`）**HTTP**: `PUT /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update. `id`, `created_at`, `messages` cannot be changed |

**Return value**: `ok(conv)` — Updated conversation object.

## Delete conversation

**handler**: `defaults.chat.delete_conversation`（`blocks/chat/delete_conversation.py`）**HTTP**: `DELETE /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |

**Return value**: `ok({"success": true})`. If not found, `error("Conversation not found", "NOT_FOUND")`.

## Send a message (with AI response)

**handler**: `defaults.chat.send`（`blocks/chat/send.py`）**HTTP**: `POST /api/chat/conversations/{id}/messages` or `POST /v1/chat/completions`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object |
| `message.role` | `string` | No | Role. Default `"user"` |
| `message.content` | `string` or `list` | Yes | Message content. If it is a string, it will be converted to `[{"type": "text", "text": ...}]` |

**Processing flow**: Save user message in `ChatStore.add_message()` → Get conversation history in `get_message_chain()` → Convert to standard format in `convert_to_standard()` → Call AI in `call_handler("defaults.ai.complete", ...)` → Build assistant message in `build_assistant_message()` → Save in `ChatStore.add_message()`.**Return value**: `ok(assistant_msg)` — AI response message object.

```json
{
  "status": "ok",
  "data": {
    "id": "uuid",
    "conversation_id": "...",
    "parent_id": "user_msg_id",
    "children_ids": [],
    "sequence_number": 2,
    "role": "assistant",
    "content": [{"type": "text", "text": "AI response"}],
    "raw_text": "AI response",
    "created_at": 1700000000000,
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    "widget": null
  }
}
```

## Add message (AI no response)

**handler**: `defaults.chat.add_message`（`blocks/chat/add_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object (role, content) |

**Return value**: `ok(msg)` — Added message object. No AI calls are made.

## Get message

**handler**: `defaults.chat.get_message`（`blocks/chat/get_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |

**Return value**: `ok(msg)` — Message object.

## Update message

**handler**: `defaults.chat.update_message`（`blocks/chat/update_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |
| `updates` | `dict` | Yes | Field to update. `id`, `conversation_id`, `created_at` cannot be changed |

**Return value**: `ok(msg)` — Updated message object.

## Delete message

**handler**: `defaults.chat.delete_message`（`blocks/chat/delete_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |

**Return value**: `ok({"success": true})`. Automatically removed from `children_ids` of the parent message. If `current_node_id` is subject to deletion, it will be updated to `parent_id`.

## Streaming transmission

**handler**: `defaults.chat.stream`（`blocks/chat/stream.py`）**HTTP**: `POST /api/chat/conversations/{id}/stream`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object |

**Processing**: Store user messages and make streaming AI calls in `call_handler("defaults.ai.stream", ...)`. `stream_id` is returned and can be used to stop the stream.**Return value**: `ok({"stream_id": "...", "conversation_id": "..."})`

## Stop streaming

**handler**: `defaults.chat.stop`（`blocks/chat/stop.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `stream_id` | `string` | No | ID of the stream to stop |

**Return value**: `ok({"success": true})`

## Regenerate AI responses

**handler**: `defaults.chat.regenerate`（`blocks/chat/regenerate.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID to be regenerated |

**Processing**: Delete specified message → Get conversation chain up to parent message → Send again to AI → Save new assistant message.**Return value**: `ok(assistant_msg)` — New AI response message.

## Branch (conversation branch)

**handler**: `defaults.chat.branch`（`blocks/chat/branch.py`）**HTTP**: Direct HTTP route is undefined. Call via `call_handler("defaults.chat.branch", ...)`.**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Original conversation ID |
| `message_id` | `string` | Yes | Branch origin message ID |

**Processing**: `ChatStore.branch()` creates a new conversation by copying the chain up to the specified message. New conversation titles will have `" (branch)"` appended to them. `parent_id` / `children_ids` in the message will be remapped to the new ID.**Return value**: `ok(new_conv)` — New branched conversation object.

## Search

**handler**: `defaults.chat.search`（`blocks/chat/search.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | Search query |
| `conversation_id` | `string` | No | To limit to a specific conversation |

**Processing**: `ChatStore.search()` performs a case-insensitive partial match search on the `raw_text` field of all messages.**Return value**: `ok({"results": [msg, msg, ...]})`

## Export

**handler**: `defaults.chat.export_conversation`（`blocks/chat/export_conversation.py`）**HTTP**: `POST /api/chat/conversations/{id}/export`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `format` | `string` | No | `"markdown"` or `"json"`. Default `"markdown"` |

**Return value**: `ok({"content": "..."})`. `domain/chat/exporter.py`, `export_markdown()` or `export_json()` are called.

## AI summary of conversation history (summarize_and_trim)

**handler**: `defaults.chat.summarize_and_trim`（`blocks/chat/summarize_and_trim.py`）**HTTP**: `POST /api/chat/conversations/{id}/summarize`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `start_message_id` | `string` | Yes | Start message ID of summary range |
| `end_message_id` | `string` | Yes | End of summary range message ID |
| `model` | `string` | No | AI model used for summarization. Use conversational model for `"default"` |
| `instruction` | `string` | No | Additional summary instructions |

**Processing**: Get messages in a specified range → Convert to standard format with `convert_to_standard()` → Build summary prompt → Let AI summarize → Delete messages in range in bulk (`delete_messages_bulk`) → Insert summary message (`insert_message_at`). Summary message `metadata` includes `is_summary: true` and `original_message_ids`.**Return value**:

```json
{
  "status": "ok",
  "data": {
    "conversation": { "...updated conversation..." },
    "summary_message": { "...summary msg..." },
    "deleted_message_ids": ["id1", "id2", "..."]
  }
}
```

## AI automatic trim suggestion for conversation history (auto_trim)

**handler**: `defaults.chat.auto_trim`（`blocks/chat/auto_trim.py`）**HTTP**: `POST /api/chat/conversations/{id}/auto-trim`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `model` | `string` | No | AI model used for analysis. Use conversational model for `"default"` |
| `max_context_tokens` | `int` | No | Target number of tokens after trimming |

**Processing**: Get all messages of the conversation → Extract text from the content of each message → Send analysis prompt to AI → AI returns summarizable segments as JSON array → Validate by checking for presence of message ID.**Return value**:

```json
{
  "status": "ok",
  "data": {
    "trim_plan": {
      "segments": [
        {
          "start_id": "msg_id_1",
          "end_id": "msg_id_5",
          "reason": "Intermediate debug outputs",
          "summary_preview": "Debugging session that resolved the issue"
        }
      ]
    },
    "conversation_id": "...",
    "total_messages": 20
  }
}
```

The actual trimming can be performed by passing each `start_id` / `end_id` of the returned `segments` to `summarize_and_trim`.

## List of all API endpoints

| method | path | handler file |
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
