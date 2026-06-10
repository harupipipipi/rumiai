<!-- docs-i18n-links:start -->
[EN](./api-reference.md) | [JP](./i18n/ja/api-reference.md) | [KR](./i18n/ko/api-reference.md) | [CN](./i18n/zh-cn/api-reference.md)
<!-- docs-i18n-links:end -->

# API Reference

All endpoints exposed by the HTTP transport (`transport/http.py`) in the defaults pack.

All responses are in JSON format and return `{"status": "ok", "data": ...}` on success and `{"status": "error", "error": {"code": "...", "message": "..."}}` on error.

CORS headers are added to all responses: `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS`, `Access-Control-Allow-Headers: Content-Type, Authorization`.

---

## Chat — conversation management

### POST /v1/chat/completions

OpenAI compatible endpoint. Send messages and get AI responses. Call `blocks.chat.send` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `conversation_id` | Required | `string` | Conversation ID |
| `message` | Required | `object` | `{"role": "user", "content": "..."}` format message |
| `message.role` | Optional | `string` | Role. Default `"user"` |
| `message.content` | Required | `string \| array` | Text string or content block array |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Assistant Message ID |
| `conversation_id` | `string` | Conversation ID |
| `role` | `string` | `"assistant"` |
| `content` | `array` | `[{"type": "text", "text": "..."}]` |
| `parent_id` | `string` | Parent message ID |
| `sequence_number` | `int` | Sequence number |
| `created_at` | `int` | Creation timestamp (milliseconds) |
| `finish_reason` | `string \| null` | `"stop"` etc. |
| `usage` | `object \| null` | `{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}` |

**Error case:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |
| `INTERNAL_ERROR` | Failed to add message |

---

### POST /api/chat/conversations

Create a new conversation. Call `blocks.chat.create_conversation` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `model` | Optional | `string` | Usage model. Default `"stub/default"` |
| `system_prompt_id` | Optional | `string` | System prompt ID |
| `agent_id` | Optional | `string` | Agent ID |
| `tags` | Optional | `array[string]` | Tag |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Conversation ID (UUID) |
| `title` | `string` | `"New Conversation"` |
| `created_at` | `int` | Creation timestamp |
| `updated_at` | `int` | Update timestamp |
| `model` | `string` | Model string |
| `system_prompt_id` | `string \| null` | System Prompt ID |
| `agent_id` | `string \| null` | Agent ID |
| `tags` | `array[string]` | Tag |
| `is_starred` | `bool` | Star state |
| `is_archived` | `bool` | Archive status |
| `current_node_id` | `string \| null` | Current node ID |
| `messages` | `array` | Message array (initially empty) |

---

### GET /api/chat/conversations

Get a list of conversations. Call `blocks.chat.list_conversations` internally.

**Request Body:** None (query parameter is not necessary because it is GET)

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `conversations` | `array[object]` | Array of conversation objects |
| `total` | `int` | Total number |

**Error case:** None (returns empty array)

---

### GET /api/chat/conversations/{id}

Get the conversation with the specified ID. The path parameter `{id}` is injected as `conversation_id`.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Response (`data`):** Conversation object (same format as Response of POST /api/chat/conversations)

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### PUT /api/chat/conversations/{id}

Update conversation metadata.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `title` | Optional | `string` | New title |
| `tags` | Optional | `array[string]` | New tag |
| `is_starred` | Optional | `bool` | Star state |
| `is_archived` | Optional | `bool` | Archive status |
| `model` | Optional | `string` | Model change |

**Response (`data`):** Updated conversation object

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### DELETE /api/chat/conversations/{id}

Delete a conversation. Call `blocks.chat.delete_conversation` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Response (`data`):** `{"success": true}`

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/messages

Send messages to conversations and get AI responses. Calls the same block (`blocks.chat.send`) as `/v1/chat/completions`, but `conversation_id` is injected from the path.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**Response (`data`):** Assistant message object (same format as POST /v1/chat/completions)

**Error case:** Same as POST /v1/chat/completions

---

### POST /api/chat/conversations/{id}/stream

Start a streaming response. Call `blocks.chat.stream` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `stream_id` | `string` | Stream ID |
| `conversation_id` | `string` | Conversation ID |

**Error case:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/export

Export conversations. Call `blocks.chat.export_conversation` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `format` | Optional | `string` | `"markdown"` or `"json"`. Default `"markdown"` |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `content` | `string` | Exported string |
| `format` | `string` | Format name |

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/summarize

Summarize and trim conversations. Call `blocks.chat.summarize_and_trim` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `start_message_id` | Required | `string` | Summary start message ID |
| `end_message_id` | Required | `string` | Summary end message ID |
| `model` | Optional | `string` | Model used for summarization |

**Response (`data`):** Summary result object

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation or message does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/chat/conversations/{id}/auto-trim

Auto-trim conversations. Call `blocks.chat.auto_trim` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `max_tokens` | Optional | `int` | Trimming threshold token count |
| `model` | Optional | `string` | Model used for summarization |

**Response (`data`):** Trimming result object

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation does not exist |

---

## Agent — agent execution

### POST /api/agent/execute

Run agent tasks. Call `blocks.agent.execute` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Description of the task to be performed |
| `tools` | Optional | `array` | Available tool definitions |
| `model` | Optional | `string` | Usage model. Default `"default"` |
| `system_prompt` | Optional | `string` | System prompt |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `execution_id` | `string` | Run ID |
| `status` | `string` | Execution state |
| `steps` | `array` | List of execution steps |

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `task` not specified |

---

### POST /api/agent/{id}/approve

Approve the agent's current step. Call `blocks.agent.approve` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**Response (`data`):** Approval result object

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/reject

Reject the agent's current step. Call `blocks.agent.reject` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**Response (`data`):** Rejection result object

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/cancel

Cancel agent execution. Call `blocks.agent.cancel` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**Response (`data`):** Cancellation result object

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### GET /api/agent/{id}/status

Get the execution status of the agent. Call `blocks.agent.status` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**Response (`data`):** Status object

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/instruct

Add runtime instructions to a running agent. Call `blocks.agent.add_instruction` internally. Instructions are injected into the message history before the next AI completion step.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id (injected as `execution_id` from path) |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `instruction` | Required | `string` | Additional instructions |
| `priority` | Optional | `string` | `"normal"` or `"urgent"`. Default `"normal"` |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `instruction_id` | `string` | Instruction ID (UUID) |
| `execution_id` | `string` | Run ID |
| `priority` | `string` | Priority |
| `status` | `string` | `"queued"` |

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` unspecified, `instruction` unspecified, run does not exist, or run is not active |

---

## Multi-Agent — multi-agent execution

### POST /api/agent/multi/execute

Start a multi-agent session. Call `blocks.agent.multi_execute` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Task description |
| `agents` | Required | `array[object]` | List of agent definitions (at least one). Each element is `{name, role, model?, system_prompt?, tools?}` |
| `orchestration` | Optional | `string` | Any of `"round_robin"`, `"directed"`, `"free"`. Default `"round_robin"` |
| `max_turns` | Optional | `int` | Maximum number of turns. Default `10`. Positive integer greater than or equal to 1 |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Session ID (`multi_` Prefix) |
| `status` | `string` | Session state (`"completed"`, `"error"`, etc.) |
| `turn_results` | `array` | Results of each turn `[{agent, type, content}, ...]` |
| `result` | `object` | Session details object |

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `task` is unspecified, `agents` is unspecified or empty, `name`/`role` of agent definition is unspecified, `orchestration` is an invalid value, `max_turns` is not a positive integer |

---

### GET /api/agent/multi/{id}/status

Get the state of a multi-agent session. Call `blocks.agent.multi_status` internally. The path parameter `{id}` is injected as `session_id`.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**Response (`data`):** Session state object (result of `session.to_dict()`)

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `session_id` is unspecified or session does not exist |

---

### POST /api/agent/multi/{id}/message

Inject messages externally into a running multi-agent session. Call `blocks.agent.multi_message` internally. The path parameter `{id}` is injected as `session_id`.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `string` | Message content to be input |
| `target_agent` | Optional | `string` | Name when addressing to a specific agent. If not specified, send as a shared message to all agents |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Session ID |
| `message` | `string` | `"Message injected successfully"` |

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | `session_id` not specified, `message` not specified, or session does not exist |

---

## Consent — Consent management

### POST /api/consent/check

Determine whether text is sensitive. Call `blocks.tool.consent_check` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `text` | Required | `string` | Judgment target text |
| `use_ai` | Optional | `bool` | Whether to use AI judgment. Default `false` |
| `model` | Optional | `string` | Model specification during AI judgment. Default `"stub/default"` |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `requires_consent` | `bool` | Whether consent is required |
| `categories` | `array[string]` | Detected categories |
| `consent_id` | `string \| null` | Consent ID if consent is required |
| `disclaimers` | `object` | Disclaimer text by category `{category: disclaimer_text}` |

**Error case:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `text` not specified |
| `INVALID_PARAM` | `text` is not a string |

---

### POST /api/consent/{id}/confirm

Record your consent or refusal. Call `blocks.tool.consent_confirm` internally. The path parameter `{id}` is injected as `consent_id`.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | consent_id |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `accepted` | Required | `bool` | Whether the user consented |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `consent_id` | `string` | Consent ID |
| `accepted` | `bool` | Consent status |
| `accepted_at` | `string \| null` | ISO 8601 timestamp if consent |

**Error case:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `consent_id` or `accepted` not specified |
| `INVALID_PARAM` | `consent_id` is not a string or `accepted` is not bool |
| `NOT_FOUND` | The specified consent_id does not exist |

---

## Prompt — Prompt management

### PUT /api/prompts/{name}

Update existing prompts. Call `blocks.prompt.update` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `content` | Optional | `string` | New body (alias for `body`) |
| `body` | Optional | `string` | New text |
| `description` | Optional | `string` | Description |
| `variables` | Optional | `array` | Variable definition |
| `metadata` | Optional | `object` | Metadata |

**Response (`data`):** Updated prompt object

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### DELETE /api/prompts/{name}

Remove prompts. Call `blocks.prompt.delete` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**Response (`data`):** `{"deleted": true}`

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### POST /api/prompts/convert

Perform mutual conversion between tool ↔ prompt. Call `blocks.prompt.convert` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `source_type` | Required | `string` | `"tool"` or `"prompt"` |
| `source_name` | Required | `string` | Source name |
| `target_type` | Required | `string` | `"tool"` or `"prompt"` |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `result` | `object` | Conversion result (tool definition or prompt object) |
| `target_type` | `string` | Destination type |

**Error case:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `source_type`/`target_type` are incorrect or identical |
| `NOT_FOUND` | Conversion source does not exist |

---

## Tool — Dynamic tool management

### POST /api/tools/create

Create dynamic tools. If handler_code is not specified, it will be automatically generated by AI. Call `blocks.tool.create` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name (same as tool_id) |
| `description` | Optional | `string` | Tool description |
| `parameters` | Required | `object` | Parameter definition in JSON Schema format |
| `handler_code` | Optional | `string` | Python handler code. If null, AI generation |
| `tags` | Optional | `array[string]` | Tag. Default `["dynamic", "user-created"]` |
| `model` | Optional | `string` | AI model used to generate handler_code |

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `tool_id` | `string` | Tool ID |
| `name` | `string` | Tool name |
| `summary` | `string` | Description |
| `handler_code` | `string` | Generated handler code |
| `created_at` | `string` | ISO 8601 timestamp |

**Error case:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `name` or `parameters` not specified |
| `INVALID_PARAM` | `parameters` is not a dict |
| `ALREADY_EXISTS` | A tool with the same name already exists |
| `REGISTER_ERROR` | Error in registration process |

---

### PUT /api/tools/{name}

Update dynamic tools. Call `blocks.tool.update` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `description` | Optional | `string` | New description |
| `parameters` | Optional | `object` | New schema |
| `handler_code` | Optional | `string` | New handler code |
| `tags` | Optional | `array[string]` | New tag |

**Response (`data`):** Updated tool definition

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### DELETE /api/tools/{name}

Delete dynamic tools. The files will also be deleted at the same time. Call `blocks.tool.delete` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**Response (`data`):** `{"deleted": true}`

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### GET /api/tools/{name}/export

Export the tool definition including handler_code. Call `blocks.tool.export` internally.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**Response (`data`):** Tool definition object (contains handler_code field)

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist |

---

## Dev — developer tools

### GET /api/dev/inspect

Get the previous request information. Call `blocks.dev.inspect` internally.

**Request Body (optional):**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Optional | `string` | Specific request ID |
| `conversation_id` | Optional | `string` | Specific conversation ID |

`request_id` When specified, returns the log. `conversation_id` When specified, returns the latest log of the conversation. Returns the previous request if both are unspecified.

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `request_id` | `string` | Request ID |
| `conversation_id` | `string` | Conversation ID |
| `model` | `string` | Usage Model |
| `prompt_used` | `string` | Prompt used |
| `tools_called` | `array` | Invoked tool |
| `context_info` | `object` | Context information |
| `timestamp` | `string` | ISO 8601 timestamp |

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Log with specified ID does not exist |

---

### GET /api/dev/prompt-history

Get prompt history. Call `blocks.dev.prompt_history` internally.

**Request Body (optional):**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `limit` | Optional | `int` | Number of results. Default 20 |

**Response (`data`):** Log array (newest first)

---

### POST /api/dev/edit-prompt

Live edit and rerun prompts. Call `blocks.dev.edit_prompt_live` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be edited |
| `new_prompt` | Required | `string` | New prompt |

**Response (`data`):** Re-execution result

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/dev/replay

Retry past requests. Call `blocks.dev.replay` internally.

**Request Body:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be re-executed |
| `model` | Optional | `string` | Rerun with another model |

**Response (`data`):** Re-execution result

**Error case:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |

---

## System — System information

### GET /api/health

Health check. Return the response directly without calling block.

**Request Body:** None

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `status` | `string` | `"healthy"` |
| `pack` | `string` | `"defaults"` |
| `ts` | `string` | ISO 8601 timestamp |

**Error case:** None

---

### GET /api/context

Get context information for a Pack. If facade is set, also returns a list of interfaces.

**Request Body:** None

**Response (`data`):**

| Field | Type | Description |
|---|---|---|
| `pack` | `string` | `"defaults"` |
| `interfaces` | `object` | Kernel facade interface list |
| `ts` | `string` | ISO 8601 timestamp |

**Error case:** None

---

## Static — static file delivery

### GET /

Returns Shell HTML. If `ui/shell.html` exists, its contents are returned. If it doesn't exist, return fallback HTML.

**Response:** `text/html` Content

---

### GET /static/{path}

Serve static files. Parent directory references with `..` are blocked.

**Path parameters:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `path` | Required | `string` | Relative path of the file |

**Response:** File contents of the corresponding Content-Type. Binary files are base64 encoded.

Corresponding extensions: `.html`, `.css`, `.js`, `.json`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.ico`

**Error case:**

| Code | Description |
|---|---|
| `ERROR` | The path is invalid (including `..`, etc.) or the file does not exist |
