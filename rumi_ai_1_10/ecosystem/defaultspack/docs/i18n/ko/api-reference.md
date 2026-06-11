<!-- docs-i18n-links:start -->
[EN](../../api-reference.md) | [JP](../ja/api-reference.md) | [KR](./api-reference.md) | [CN](../zh-cn/api-reference.md)
<!-- docs-i18n-links:end -->

# API 참조

기본 팩의 HTTP 전송(`transport/http.py`)에 의해 노출되는 모든 엔드포인트입니다.

모든 응답은 JSON 형식이며 성공 시 `{"status": "ok", "data": ...}`, 오류 시 `{"status": "error", "error": {"code": "...", "message": "..."}}`을 반환합니다.

CORS 헤더는 모든 응답에 추가됩니다: `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS`, `Access-Control-Allow-Headers: Content-Type, Authorization`.

---

## 채팅 — 대화 관리

### POST /v1/chat/completions

OpenAI 호환 엔드포인트. 메시지를 보내고 AI 응답을 받으세요. 내부적으로 `blocks.chat.send`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `conversation_id` | Required | `string` | Conversation ID |
| `message` | Required | `object` | `{"role": "user", "content": "..."}` format message |
| `message.role` | Optional | `string` | Role. Default `"user"` |
| `message.content` | Required | `string \| array` | Text string or content block array |

**답변(`data`):**

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

**오류 사례:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |
| `INTERNAL_ERROR` | Failed to add message |

---

### POST /api/chat/대화

새 대화를 만듭니다. 내부적으로 `blocks.chat.create_conversation`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `model` | Optional | `string` | Usage model. Default `"stub/default"` |
| `system_prompt_id` | Optional | `string` | System prompt ID |
| `agent_id` | Optional | `string` | Agent ID |
| `tags` | Optional | `array[string]` | Tag |

**답변(`data`):**

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

대화 목록을 가져옵니다. 내부적으로 `blocks.chat.list_conversations`을 호출하세요.

**요청 본문:** 없음(쿼리 매개변수는 GET이므로 필요하지 않음)**응답(`data`):**

| Field | Type | Description |
|---|---|---|
| `conversations` | `array[object]` | Array of conversation objects |
| `total` | `int` | Total number |

**오류 사례:** 없음(빈 배열 반환)

---

### GET /api/chat/conversations/{id}

지정된 ID로 대화를 가져옵니다. 경로 매개변수 `{id}`는 `conversation_id`으로 주입됩니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**응답(`data`):** 대화 개체(POST /api/chat/conversations의 응답과 동일한 형식)**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### PUT /api/chat/conversations/{id}

대화 메타데이터를 업데이트합니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `title` | Optional | `string` | New title |
| `tags` | Optional | `array[string]` | New tag |
| `is_starred` | Optional | `bool` | Star state |
| `is_archived` | Optional | `bool` | Archive status |
| `model` | Optional | `string` | Model change |

**응답(`data`):** 업데이트된 대화 개체**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### 삭제 /api/chat/conversations/{id}

대화를 삭제합니다. 내부적으로 `blocks.chat.delete_conversation`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**응답(`data`):** `{"success": true}`**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/messages

대화에 메시지를 보내고 AI 응답을 받으세요. `/v1/chat/completions`과 동일한 블록(`blocks.chat.send`)을 호출하지만 경로에서 `conversation_id`가 삽입됩니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**응답(`data`):** 보조 메시지 개체(POST /v1/chat/completions와 동일한 형식)**오류 사례:** POST /v1/chat/completions와 동일

---

### POST /api/chat/conversations/{id}/stream

스트리밍 응답을 시작합니다. 내부적으로 `blocks.chat.stream`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `stream_id` | `string` | Stream ID |
| `conversation_id` | `string` | Conversation ID |

**오류 사례:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/export

대화를 내보냅니다. 내부적으로 `blocks.chat.export_conversation`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `format` | Optional | `string` | `"markdown"` or `"json"`. Default `"markdown"` |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `content` | `string` | Exported string |
| `format` | `string` | Format name |

**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/summarize

대화를 요약하고 다듬습니다. 내부적으로 `blocks.chat.summarize_and_trim`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `start_message_id` | Required | `string` | Summary start message ID |
| `end_message_id` | Required | `string` | Summary end message ID |
| `model` | Optional | `string` | Model used for summarization |

**응답(`data`):** 요약 결과 개체**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation or message does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/chat/conversations/{id}/auto-trim

대화를 자동으로 자릅니다. 내부적으로 `blocks.chat.auto_trim`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `max_tokens` | Optional | `int` | Trimming threshold token count |
| `model` | Optional | `string` | Model used for summarization |

**응답(`data`):** 트리밍 결과 개체**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation does not exist |

---

## 에이전트 — 에이전트 실행

### POST /api/agent/execute

에이전트 작업을 실행합니다. 내부적으로 `blocks.agent.execute`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Description of the task to be performed |
| `tools` | Optional | `array` | Available tool definitions |
| `model` | Optional | `string` | Usage model. Default `"default"` |
| `system_prompt` | Optional | `string` | System prompt |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `execution_id` | `string` | Run ID |
| `status` | `string` | Execution state |
| `steps` | `array` | List of execution steps |

**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `task` not specified |

---

### POST /api/agent/{id}/approve

에이전트의 현재 단계를 승인합니다. 내부적으로 `blocks.agent.approve`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**응답(`data`):** 승인 결과 개체**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/reject

에이전트의 현재 단계를 거부합니다. 내부적으로 `blocks.agent.reject`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**응답(`data`):** 거부 결과 개체**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/cancel

에이전트 실행을 취소합니다. 내부적으로 `blocks.agent.cancel`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**응답(`data`):** 취소 결과 개체**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### GET /api/agent/{id}/status

에이전트의 실행 상태를 가져옵니다. 내부적으로 `blocks.agent.status`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**응답(`data`):** 상태 개체**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/instruct

실행 중인 에이전트에 런타임 지침을 추가합니다. 내부적으로 `blocks.agent.add_instruction`을 호출하세요. 다음 AI 완료 단계 전에 지침이 메시지 기록에 삽입됩니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id (injected as `execution_id` from path) |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `instruction` | Required | `string` | Additional instructions |
| `priority` | Optional | `string` | `"normal"` or `"urgent"`. Default `"normal"` |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `instruction_id` | `string` | Instruction ID (UUID) |
| `execution_id` | `string` | Run ID |
| `priority` | `string` | Priority |
| `status` | `string` | `"queued"` |

**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` unspecified, `instruction` unspecified, run does not exist, or run is not active |

---

## 회사 작업 공간 호환성 - 레거시 다중 에이전트 엔드포인트

### POST /api/agent/multi/execute

호환성 끝점. 내부적으로 회사 메시지는 `CompanySlackRuntime`에 게시되고 멘션/작업/AgentEngine이 실행될 때 비동기적으로 라우팅됩니다. 응답에는 `deprecation_warning`이 포함됩니다.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Task description |
| `agents` | Required | `array[object]` | List of agent definitions (at least one). Each element is `{name, role, model?, system_prompt?, tools?}` |
| `company_id` | Optional | `string` | Route to company workspace. If not specified, default company |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Compatible session id. The entity is company thread id |
| `status` | `string` | Routing state |
| `turn_results` | `array` | Empty array for compatibility |
| `result` | `object` | CompanySlackRuntime routing result |
| `deprecation_warning` | `string` | Compatible wrapper announcement |

**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `task` is not specified or company workspace routing fails |

---

### GET /api/agent/multi/{id}/status

호환되는 세션 ID에 해당하는 회사 스레드의 메시지/작업을 가져옵니다. 경로 매개변수 `{id}`는 `session_id`으로 주입됩니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**응답(`data`):** 회사 스레드 상태, 메시지, 작업 및 호환성 경고.**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `session_id` not specified |

---

### POST /api/agent/multi/{id}/message

호환되는 세션 스레드에 메시지를 게시합니다. 언급은 활성 실행 또는 AgentEngine 위임 작업에 대한 런타임 지침으로 처리됩니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `string` | Message content to be input |
| `target_agent` | Optional | `string` | Name when addressing to a specific agent. If not specified, send as a shared message to all agents |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Session ID |
| `message` | `string` | `"Message injected successfully"` |

**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | `session_id` not specified, `message` not specified, or session does not exist |

---

## 동의 — 동의 관리

### POST /api/consent/check

텍스트가 민감한지 여부를 확인합니다. 내부적으로 `blocks.tool.consent_check`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `text` | Required | `string` | Judgment target text |
| `use_ai` | Optional | `bool` | Whether to use AI judgment. Default `false` |
| `model` | Optional | `string` | Model specification during AI judgment. Default `"stub/default"` |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `requires_consent` | `bool` | Whether consent is required |
| `categories` | `array[string]` | Detected categories |
| `consent_id` | `string \| null` | Consent ID if consent is required |
| `disclaimers` | `object` | Disclaimer text by category `{category: disclaimer_text}` |

**오류 사례:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `text` not specified |
| `INVALID_PARAM` | `text` is not a string |

---

### POST /api/consent/{id}/confirm

동의 또는 거부를 기록하십시오. 내부적으로 `blocks.tool.consent_confirm`을 호출하세요. 경로 매개변수 `{id}`은 `consent_id`로 주입됩니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | consent_id |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `accepted` | Required | `bool` | Whether the user consented |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `consent_id` | `string` | Consent ID |
| `accepted` | `bool` | Consent status |
| `accepted_at` | `string \| null` | ISO 8601 timestamp if consent |

**오류 사례:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `consent_id` or `accepted` not specified |
| `INVALID_PARAM` | `consent_id` is not a string or `accepted` is not bool |
| `NOT_FOUND` | The specified consent_id does not exist |

---

## 프롬프트 - 프롬프트 관리

### PUT /api/prompts/{이름}

기존 프롬프트를 업데이트합니다. 내부적으로 `blocks.prompt.update`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `content` | Optional | `string` | New body (alias for `body`) |
| `body` | Optional | `string` | New text |
| `description` | Optional | `string` | Description |
| `variables` | Optional | `array` | Variable definition |
| `metadata` | Optional | `object` | Metadata |

**응답(`data`):** 프롬프트 개체 업데이트됨**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### 삭제 /api/prompts/{이름}

프롬프트를 제거합니다. 내부적으로 `blocks.prompt.delete`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**응답(`data`):** `{"deleted": true}`**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### POST /api/프롬프트/변환

도구 ⇔ 프롬프트 간의 상호 변환을 수행합니다. 내부적으로 `blocks.prompt.convert`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `source_type` | Required | `string` | `"tool"` or `"prompt"` |
| `source_name` | Required | `string` | Source name |
| `target_type` | Required | `string` | `"tool"` or `"prompt"` |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `result` | `object` | Conversion result (tool definition or prompt object) |
| `target_type` | `string` | Destination type |

**오류 사례:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `source_type`/`target_type` are incorrect or identical |
| `NOT_FOUND` | Conversion source does not exist |

---

## 도구 - 동적 도구 관리

### POST /api/tools/create

동적 도구를 만듭니다. handler_code를 지정하지 않으면 AI에 의해 자동으로 생성됩니다. 내부적으로 `blocks.tool.create`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name (same as tool_id) |
| `description` | Optional | `string` | Tool description |
| `parameters` | Required | `object` | Parameter definition in JSON Schema format |
| `handler_code` | Optional | `string` | Python handler code. If null, AI generation |
| `tags` | Optional | `array[string]` | Tag. Default `["dynamic", "user-created"]` |
| `model` | Optional | `string` | AI model used to generate handler_code |

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `tool_id` | `string` | Tool ID |
| `name` | `string` | Tool name |
| `summary` | `string` | Description |
| `handler_code` | `string` | Generated handler code |
| `created_at` | `string` | ISO 8601 timestamp |

**오류 사례:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `name` or `parameters` not specified |
| `INVALID_PARAM` | `parameters` is not a dict |
| `ALREADY_EXISTS` | A tool with the same name already exists |
| `REGISTER_ERROR` | Error in registration process |

---

### PUT /api/tools/{이름}

동적 도구를 업데이트합니다. 내부적으로 `blocks.tool.update`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `description` | Optional | `string` | New description |
| `parameters` | Optional | `object` | New schema |
| `handler_code` | Optional | `string` | New handler code |
| `tags` | Optional | `array[string]` | New tag |

**응답(`data`):** 업데이트된 도구 정의**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### 삭제 /api/tools/{이름}

동적 도구를 삭제합니다. 동시에 파일도 삭제됩니다. 내부적으로 `blocks.tool.delete`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**응답(`data`):** `{"deleted": true}`**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### GET /api/tools/{이름}/export

handler_code를 포함하여 도구 정의를 내보냅니다. 내부적으로 `blocks.tool.export`을 호출하세요.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**응답(`data`):** 도구 정의 개체(handler_code 필드 포함)**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist |

---

## 개발 — 개발자 도구

### GET /api/dev/inspect

이전 요청 정보를 가져옵니다. 내부적으로 `blocks.dev.inspect`을 호출하세요.

**요청 본문(선택 사항):**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Optional | `string` | Specific request ID |
| `conversation_id` | Optional | `string` | Specific conversation ID |

`request_id` 지정되면 로그를 반환합니다. `conversation_id` 지정되면 대화의 최신 로그를 반환합니다. 둘 다 지정되지 않은 경우 이전 요청을 반환합니다.

**답변(`data`):**

| Field | Type | Description |
|---|---|---|
| `request_id` | `string` | Request ID |
| `conversation_id` | `string` | Conversation ID |
| `model` | `string` | Usage Model |
| `prompt_used` | `string` | Prompt used |
| `tools_called` | `array` | Invoked tool |
| `context_info` | `object` | Context information |
| `timestamp` | `string` | ISO 8601 timestamp |

**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Log with specified ID does not exist |

---

### GET /api/dev/prompt-history

프롬프트 기록을 얻으십시오. 내부적으로 `blocks.dev.prompt_history`을 호출하세요.

**요청 본문(선택 사항):**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `limit` | Optional | `int` | Number of results. Default 20 |

**응답(`data`):** 로그 배열(최신 항목순)

---

### POST /api/dev/edit-prompt

실시간 편집 및 재실행 프롬프트. 내부적으로 `blocks.dev.edit_prompt_live`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be edited |
| `new_prompt` | Required | `string` | New prompt |

**응답(`data`):** 재실행 결과**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/dev/replay

과거 요청을 다시 시도하세요. 내부적으로 `blocks.dev.replay`을 호출하세요.

**요청 본문:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be re-executed |
| `model` | Optional | `string` | Rerun with another model |

**응답(`data`):** 재실행 결과**오류 사례:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |

---

## 시스템 — 시스템 정보

### GET /api/건강

건강검진. 블록을 호출하지 않고 직접 응답을 반환합니다.

**요청 본문:** 없음**응답(`data`):**

| Field | Type | Description |
|---|---|---|
| `status` | `string` | `"healthy"` |
| `pack` | `string` | `"defaults"` |
| `ts` | `string` | ISO 8601 timestamp |

**오류 사례:** 없음

---

### GET /api/컨텍스트

팩에 대한 컨텍스트 정보를 가져옵니다. Facade가 설정된 경우 인터페이스 목록도 반환합니다.

**요청 본문:** 없음**응답(`data`):**

| Field | Type | Description |
|---|---|---|
| `pack` | `string` | `"defaults"` |
| `interfaces` | `object` | Kernel facade interface list |
| `ts` | `string` | ISO 8601 timestamp |

**오류 사례:** 없음

---

## 정적 — 정적 파일 전달

### 받기 /

쉘 HTML을 반환합니다. `ui/shell.html`이 있으면 해당 내용이 반환됩니다. 존재하지 않는 경우 대체 HTML을 반환합니다.

**답변:** `text/html` 콘텐츠

---

### GET /static/{경로}

정적 파일을 제공합니다. `..`이 포함된 상위 디렉터리 참조는 차단됩니다.

**경로 매개변수:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `path` | Required | `string` | Relative path of the file |

**응답:** 해당 Content-Type의 파일 콘텐츠입니다. 바이너리 파일은 base64로 인코딩됩니다.

해당 확장자: `.html`, `.css`, `.js`, `.json`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.ico`

**오류 사례:**

| Code | Description |
|---|---|
| `ERROR` | The path is invalid (including `..`, etc.) or the file does not exist |
