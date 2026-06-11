<!-- docs-i18n-links:start -->
[EN](../../api-reference.md) | [JP](../ja/api-reference.md) | [KR](../ko/api-reference.md) | [CN](./api-reference.md)
<!-- docs-i18n-links:end -->

# API 参考

默认包中 HTTP 传输 (`transport/http.py`) 公开的所有端点。

所有响应均采用 JSON 格式，成功时返回 `{"status": "ok", "data": ...}`，错误时返回 `{"status": "error", "error": {"code": "...", "message": "..."}}`。

CORS 标头添加到所有响应中：`Access-Control-Allow-Origin: *`、`Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS`、`Access-Control-Allow-Headers: Content-Type, Authorization`。

---

## 聊天 — 对话管理

### POST /v1/chat/completions

OpenAI 兼容端点。发送消息并获得 AI 回复。内部调用`blocks.chat.send`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `conversation_id` | Required | `string` | Conversation ID |
| `message` | Required | `object` | `{"role": "user", "content": "..."}` format message |
| `message.role` | Optional | `string` | Role. Default `"user"` |
| `message.content` | Required | `string \| array` | Text string or content block array |

**回应（`data`）：**

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

**错误情况：**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |
| `INTERNAL_ERROR` | Failed to add message |

---

### POST /api/chat/conversations

创建一个新对话。内部调用`blocks.chat.create_conversation`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `model` | Optional | `string` | Usage model. Default `"stub/default"` |
| `system_prompt_id` | Optional | `string` | System prompt ID |
| `agent_id` | Optional | `string` | Agent ID |
| `tags` | Optional | `array[string]` | Tag |

**回应（`data`）：**

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

### 获取/api/聊天/对话

获取对话列表。内部调用`blocks.chat.list_conversations`。

**请求正文：**无（查询参数不是必需的，因为它是 GET）**响应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `conversations` | `array[object]` | Array of conversation objects |
| `total` | `int` | Total number |

**错误情况：** None（返回空数组）

---

### GET /api/chat/conversations/{id}

获取指定ID的会话。路径参数`{id}`被注入为`conversation_id`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**响应 (`data`):** 对话对象（与 POST /api/chat/conversations 的响应格式相同）**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### PUT /api/chat/conversations/{id}

更新对话元数据。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `title` | Optional | `string` | New title |
| `tags` | Optional | `array[string]` | New tag |
| `is_starred` | Optional | `bool` | Star state |
| `is_archived` | Optional | `bool` | Archive status |
| `model` | Optional | `string` | Model change |

**响应（`data`）：**更新的对话对象**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### 删除 /api/chat/conversations/{id}

删除对话。内部调用`blocks.chat.delete_conversation`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**响应（`data`）：** `{"success": true}`**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/messages

向对话发送消息并获得 AI 回复。调用与 `/v1/chat/completions` 相同的块 (`blocks.chat.send`)，但 `conversation_id` 是从路径注入的。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**响应（`data`）：**助理消息对象（与 POST /v1/chat/completions 格式相同）**错误情况：**与 POST /v1/chat/completions 相同

---

### POST /api/chat/conversations/{id}/stream

开始流式响应。内部调用`blocks.chat.stream`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `stream_id` | `string` | Stream ID |
| `conversation_id` | `string` | Conversation ID |

**错误情况：**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/export

导出对话。内部调用`blocks.chat.export_conversation`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `format` | Optional | `string` | `"markdown"` or `"json"`. Default `"markdown"` |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `content` | `string` | Exported string |
| `format` | `string` | Format name |

**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/summarize

总结并修剪对话。内部调用`blocks.chat.summarize_and_trim`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `start_message_id` | Required | `string` | Summary start message ID |
| `end_message_id` | Required | `string` | Summary end message ID |
| `model` | Optional | `string` | Model used for summarization |

**响应（`data`）：**汇总结果对象**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation or message does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/chat/conversations/{id}/auto-trim

自动修剪对话。内部调用`blocks.chat.auto_trim`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `max_tokens` | Optional | `int` | Trimming threshold token count |
| `model` | Optional | `string` | Model used for summarization |

**响应（`data`）：**修剪结果对象**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation does not exist |

---

## Agent — 代理执行

### POST /api/agent/execute

运行代理任务。内部调用`blocks.agent.execute`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Description of the task to be performed |
| `tools` | Optional | `array` | Available tool definitions |
| `model` | Optional | `string` | Usage model. Default `"default"` |
| `system_prompt` | Optional | `string` | System prompt |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `execution_id` | `string` | Run ID |
| `status` | `string` | Execution state |
| `steps` | `array` | List of execution steps |

**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `task` not specified |

---

### POST /api/agent/{id}/approve

批准代理的当前步骤。内部调用`blocks.agent.approve`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**响应（`data`）：**审批结果对象**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/reject

拒绝代理的当前步骤。内部调用`blocks.agent.reject`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**响应（`data`）：**拒绝结果对象**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/取消

取消代理执行。内部调用`blocks.agent.cancel`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**响应（`data`）：**取消结果对象**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### GET /api/agent/{id}/status

获取代理的执行状态。内部调用`blocks.agent.status`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**响应（`data`）：**状态对象**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/instruct

将运行时指令添加到正在运行的代理。内部调用`blocks.agent.add_instruction`。在下一个 AI 完成步骤之前，指令将被注入到消息历史记录中。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id (injected as `execution_id` from path) |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `instruction` | Required | `string` | Additional instructions |
| `priority` | Optional | `string` | `"normal"` or `"urgent"`. Default `"normal"` |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `instruction_id` | `string` | Instruction ID (UUID) |
| `execution_id` | `string` | Run ID |
| `priority` | `string` | Priority |
| `status` | `string` | `"queued"` |

**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` unspecified, `instruction` unspecified, run does not exist, or run is not active |

---

## 公司工作空间兼容性 — 传统多代理端点

### POST /api/agent/multi/execute

兼容性端点。在内部，公司消息发布到 `CompanySlackRuntime`，并在提及/任务/AgentEngine 运行时异步路由。响应包括`deprecation_warning`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Task description |
| `agents` | Required | `array[object]` | List of agent definitions (at least one). Each element is `{name, role, model?, system_prompt?, tools?}` |
| `company_id` | Optional | `string` | Route to company workspace. If not specified, default company |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Compatible session id. The entity is company thread id |
| `status` | `string` | Routing state |
| `turn_results` | `array` | Empty array for compatibility |
| `result` | `object` | CompanySlackRuntime routing result |
| `deprecation_warning` | `string` | Compatible wrapper announcement |

**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `task` is not specified or company workspace routing fails |

---

### GET /api/agent/multi/{id}/status

获取兼容会话id对应的公司线程的消息/任务。路径参数`{id}`被注入为`session_id`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**响应（`data`）：**公司线程状态、消息、任务和兼容性警告。**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `session_id` not specified |

---

### POST /api/agent/multi/{id}/message

将消息发布到兼容的会话线程。提及被视为主动运行或 AgentEngine 委派任务的运行时指令。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `string` | Message content to be input |
| `target_agent` | Optional | `string` | Name when addressing to a specific agent. If not specified, send as a shared message to all agents |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Session ID |
| `message` | `string` | `"Message injected successfully"` |

**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | `session_id` not specified, `message` not specified, or session does not exist |

---

## 同意——同意管理

### POST /api/同意/检查

确定文本是否敏感。内部调用`blocks.tool.consent_check`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `text` | Required | `string` | Judgment target text |
| `use_ai` | Optional | `bool` | Whether to use AI judgment. Default `false` |
| `model` | Optional | `string` | Model specification during AI judgment. Default `"stub/default"` |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `requires_consent` | `bool` | Whether consent is required |
| `categories` | `array[string]` | Detected categories |
| `consent_id` | `string \| null` | Consent ID if consent is required |
| `disclaimers` | `object` | Disclaimer text by category `{category: disclaimer_text}` |

**错误情况：**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `text` not specified |
| `INVALID_PARAM` | `text` is not a string |

---

### POST /api/consent/{id}/confirm

记录您的同意或拒绝。内部调用`blocks.tool.consent_confirm`。路径参数`{id}`被注入为`consent_id`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | consent_id |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `accepted` | Required | `bool` | Whether the user consented |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `consent_id` | `string` | Consent ID |
| `accepted` | `bool` | Consent status |
| `accepted_at` | `string \| null` | ISO 8601 timestamp if consent |

**错误情况：**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `consent_id` or `accepted` not specified |
| `INVALID_PARAM` | `consent_id` is not a string or `accepted` is not bool |
| `NOT_FOUND` | The specified consent_id does not exist |

---

## Prompt — 及时管理

### PUT /api/prompts/{name}

更新现有提示。内部调用`blocks.prompt.update`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `content` | Optional | `string` | New body (alias for `body`) |
| `body` | Optional | `string` | New text |
| `description` | Optional | `string` | Description |
| `variables` | Optional | `array` | Variable definition |
| `metadata` | Optional | `object` | Metadata |

**响应（`data`）：**更新提示对象**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### 删除 /api/prompts/{name}

删除提示。内部调用`blocks.prompt.delete`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**响应（`data`）：** `{"deleted": true}`**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### POST /api/prompts/convert

进行工具↔提示之间的相互转换。内部调用`blocks.prompt.convert`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `source_type` | Required | `string` | `"tool"` or `"prompt"` |
| `source_name` | Required | `string` | Source name |
| `target_type` | Required | `string` | `"tool"` or `"prompt"` |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `result` | `object` | Conversion result (tool definition or prompt object) |
| `target_type` | `string` | Destination type |

**错误情况：**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `source_type`/`target_type` are incorrect or identical |
| `NOT_FOUND` | Conversion source does not exist |

---

## Tool — 动态工具管理

### POST /api/tools/create

创建动态工具。如果不指定handler_code，它将由AI自动生成。内部调用`blocks.tool.create`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name (same as tool_id) |
| `description` | Optional | `string` | Tool description |
| `parameters` | Required | `object` | Parameter definition in JSON Schema format |
| `handler_code` | Optional | `string` | Python handler code. If null, AI generation |
| `tags` | Optional | `array[string]` | Tag. Default `["dynamic", "user-created"]` |
| `model` | Optional | `string` | AI model used to generate handler_code |

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `tool_id` | `string` | Tool ID |
| `name` | `string` | Tool name |
| `summary` | `string` | Description |
| `handler_code` | `string` | Generated handler code |
| `created_at` | `string` | ISO 8601 timestamp |

**错误情况：**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `name` or `parameters` not specified |
| `INVALID_PARAM` | `parameters` is not a dict |
| `ALREADY_EXISTS` | A tool with the same name already exists |
| `REGISTER_ERROR` | Error in registration process |

---

### PUT /api/tools/{名称}

更新动态工具。内部调用`blocks.tool.update`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `description` | Optional | `string` | New description |
| `parameters` | Optional | `object` | New schema |
| `handler_code` | Optional | `string` | New handler code |
| `tags` | Optional | `array[string]` | New tag |

**响应（`data`）：**更新了工具定义**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### 删除 /api/tools/{name}

删除动态工具。文件也会同时被删除。内部调用`blocks.tool.delete`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**响应（`data`）：** `{"deleted": true}`**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### GET /api/tools/{name}/export

导出工具定义，包括 handler_code。内部调用`blocks.tool.export`。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**响应（`data`）：**工具定义对象（包含handler_code字段）**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist |

---

## Dev——开发者工具

### 获取/api/dev/inspect

获取之前的请求信息。内部调用`blocks.dev.inspect`。

**请求正文（可选）：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Optional | `string` | Specific request ID |
| `conversation_id` | Optional | `string` | Specific conversation ID |

`request_id` 指定时，返回日志。 `conversation_id` 如果指定，则返回最新的对话日志。如果两者均未指定，则返回前一个请求。

**回应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `request_id` | `string` | Request ID |
| `conversation_id` | `string` | Conversation ID |
| `model` | `string` | Usage Model |
| `prompt_used` | `string` | Prompt used |
| `tools_called` | `array` | Invoked tool |
| `context_info` | `object` | Context information |
| `timestamp` | `string` | ISO 8601 timestamp |

**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | Log with specified ID does not exist |

---

### 获取 /api/dev/prompt-history

获取即时历史记录。内部调用`blocks.dev.prompt_history`。

**请求正文（可选）：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `limit` | Optional | `int` | Number of results. Default 20 |

**响应（`data`）：** 日志数组（最新的在前）

---

### POST /api/dev/edit-prompt

实时编辑和重新运行提示。内部调用`blocks.dev.edit_prompt_live`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be edited |
| `new_prompt` | Required | `string` | New prompt |

**响应(`data`)：**重新执行结果**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/dev/replay

重试过去的请求。内部调用`blocks.dev.replay`。

**请求正文：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be re-executed |
| `model` | Optional | `string` | Rerun with another model |

**响应(`data`)：**重新执行结果**错误情况：**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |

---

## 系统——系统信息

### 获取/api/health

健康检查。直接返回响应而不调用block。

**请求正文：**无**响应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `status` | `string` | `"healthy"` |
| `pack` | `string` | `"defaults"` |
| `ts` | `string` | ISO 8601 timestamp |

**错误情况：**无

---

### 获取/api/上下文

获取包的上下文信息。如果设置了外观，还返回接口列表。

**请求正文：**无**响应（`data`）：**

| Field | Type | Description |
|---|---|---|
| `pack` | `string` | `"defaults"` |
| `interfaces` | `object` | Kernel facade interface list |
| `ts` | `string` | ISO 8601 timestamp |

**错误情况：**无

---

## Static — 静态文件传递

### 获取/

返回 Shell HTML。如果`ui/shell.html`存在，则返回其内容。如果不存在，则返回后备 HTML。

**回复：** `text/html` 内容

---

### 获取/静态/{路径}

提供静态文件。带有 `..` 的父目录引用将被阻止。

**路径参数：**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `path` | Required | `string` | Relative path of the file |

**响应：** 对应Content-Type的文件内容。二进制文件采用 Base64 编码。

对应扩展： `.html`、`.css`、`.js`、`.json`、`.png`、`.jpg`、`.jpeg`、`.gif`、`.svg`、`.ico`

**错误情况：**

| Code | Description |
|---|---|
| `ERROR` | The path is invalid (including `..`, etc.) or the file does not exist |
