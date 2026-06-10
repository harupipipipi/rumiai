<!-- docs-i18n-links:start -->
[EN](../../api-reference.md) | [JP](../ja/api-reference.md) | [KR](./api-reference.md) | [CN](../zh-cn/api-reference.md)
<!-- docs-i18n-links:end -->

# API Reference

defaults Pack의 HTTP transport(`transport/http.py`)가 게시하는 모든 엔드포인트.

모든 응답은 JSON 형식으로 성공하면 `{"status": "ok", "data": ...}`, 오류가 발생하면 `{"status": "error", "error": {"code": "...", "message": "..."}}`을 반환합니다.

CORS 헤더는 모든 응답에 부여됩니다 : `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS`, `Access-Control-Allow-Headers: Content-Type, Authorization`.

---

## Chat — 대화 관리

### POST /v1/chat/completions

OpenAI 호환 엔드포인트. 메시지를 보내 AI 응답을 얻습니다. 내부에서 `blocks.chat.send`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `conversation_id` | 필수 | `string` | 대화 ID |
| `message` | 필수 | `object` | `{"role": "user", "content": "..."}` 형식 메시지 |
| `message.role` | 선택 | `string` | 역할. 기본 `"user"` |
| `message.content` | 필수 | `string \| array` | 텍스트 문자열 또는 content block 배열 |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `id` | `string` | 어시스턴트 메시지 ID |
| `conversation_id` | `string` | 대화 ID |
| `role` | `string` | `"assistant"` |
| `content` | `array` | `[{"type": "text", "text": "..."}]` |
| `parent_id` | `string` | 상위 메시지 ID |
| `sequence_number` | `int` | 시퀀스 번호 |
| `created_at` | `int` | 작성 타임스탬프(밀리초) |
| `finish_reason` | `string \| null` | `"stop"` 등 |
| `usage` | `object \| null` | `{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}` |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `INVALID_INPUT` |`conversation_id` 또는 `message`가 지정되지 않음 |
| `NOT_FOUND` | 지정된 대화가 존재하지 않음 |
| `INTERNAL_ERROR` | 메시지 추가 실패 |

---

### POST /api/chat/conversations

새로운 대화를 만듭니다. 내부에서 `blocks.chat.create_conversation`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `model` | 선택적 | `string` | 사용 모델. 기본 `"stub/default"` |
| `system_prompt_id` | 선택적 | `string` | 시스템 프롬프트 ID |
| `agent_id` | 선택적 | `string` | 에이전트 ID |
| `tags` | 선택적 | `array[string]` | 태그 |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `id` | `string` | 대화 ID(UUID) |
| `title` | `string` | `"New Conversation"` |
| `created_at` | `int` | 작성 타임스탬프 |
| `updated_at` | `int` | 업데이트 타임스탬프 |
| `model` | `string` | 모델 문자열 |
| `system_prompt_id` | `string \| null` | 시스템 프롬프트 ID |
| `agent_id` | `string \| null` | 에이전트 ID |
| `tags` | `array[string]` | 태그 |
| `is_starred` | `bool` | 스타 상태 |
| `is_archived` | `bool` | 아카이브 상태 |
| `current_node_id` | `string \| null` | 현재 노드 ID |
| `messages` | `array` | 메시지 배열(초기에는 비어 있음) |

---

### GET /api/chat/conversations

대화 목록을 가져옵니다. 내부에서 `blocks.chat.list_conversations`를 호출합니다.

**Request Body:** 없음(GET 때문에 쿼리 매개 변수는 Body 필요 없음)

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `conversations` | `array[object]` | 대화 객체 배열 |
| `total` | `int` | 총 건수 |

**오류 사례:** 없음(빈 배열 반환)

---

### GET /api/chat/conversations/{id}

지정된 ID의 대화를 가져옵니다. 경로 매개 변수 `{id}`가 `conversation_id`로 주입됩니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Response(`data`):** 대화 객체(POST /api/chat/conversations의 Response와 동일한 형식)

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 대화가 존재하지 않음 |

---

### PUT /api/chat/conversations/{id}

대화 메타데이터를 업데이트합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `title` | 선택적 | `string` | 새로운 제목 |
| `tags` | 선택 사항 | `array[string]` | 새 태그 |
| `is_starred` | 선택적 | `bool` | 스타 상태 |
| `is_archived` | 선택적 | `bool` | 아카이브 상태 |
| `model` | 선택적 | `string` | 모델 변경 |

**Response (`data`):** 업데이트 후 대화 객체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 대화가 존재하지 않음 |

---

### DELETE /api/chat/conversations/{id}

대화를 삭제합니다. 내부에서 `blocks.chat.delete_conversation`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Response (`data`):** `{"success": true}`

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 대화가 존재하지 않음 |

---

### POST /api/chat/conversations/{id}/messages

대화에 메시지를 보내 AI 응답을 받습니다. `/v1/chat/completions`와 동일한 block(`blocks.chat.send`)를 호출하지만, `conversation_id`가 경로에서 주입됩니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `message` | 필수 | `object` | `{"role": "user", "content": "..."}` |

**Response(`data`):** 어시스턴트 메시지 객체(POST /v1/chat/completions와 동일한 형식)

**오류 사례:** POST /v1/chat/completions와 동일

---

### POST /api/chat/conversations/{id}/stream

스트리밍 응답을 시작합니다. 내부에서 `blocks.chat.stream`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `message` | 필수 | `object` | `{"role": "user", "content": "..."}` |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `stream_id` | `string` | 스트림 ID |
| `conversation_id` | `string` | 대화 ID |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `INVALID_INPUT` |`conversation_id` 또는 `message`가 지정되지 않음 |
| `NOT_FOUND` | 지정된 대화가 존재하지 않음 |

---

### POST /api/chat/conversations/{id}/export

대화를 내보냅니다. 내부에서 `blocks.chat.export_conversation`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `format` | 선택 | `string` | `"markdown"` 또는 `"json"`. 기본 `"markdown"` |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `content` | `string` | 내보낸 문자열 |
| `format` | `string` | 형식 이름 |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 대화가 존재하지 않음 |

---

### POST /api/chat/conversations/{id}/summarize

대화를 요약하고 잘라냅니다. 내부에서 `blocks.chat.summarize_and_trim`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `start_message_id` | 필수 | `string` | 요약 시작 메시지 ID |
| `end_message_id` | 필수 | `string` | 요약 종료 메시지 ID |
| `model` | 선택적 | `string` | 요약에 사용되는 모델 |

**Response (`data`):** 요약 결과 개체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 대화 또는 메시지가 존재하지 않음 |
| `INVALID_INPUT` | 필수 매개변수 부족 |

---

### POST /api/chat/conversations/{id}/auto-trim

대화를 자동 자르기. 내부에서 `blocks.chat.auto_trim`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | 대화 ID |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `max_tokens` | 선택적 | `int` | 트리밍 임계값 토큰 수 |
| `model` | 선택적 | `string` | 요약에 사용되는 모델 |

**Response (`data`):** 트리밍 결과 객체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 대화가 존재하지 않음 |

---

## Agent — 에이전트 실행

### POST /api/agent/execute

에이전트 작업을 수행합니다. 내부에서 `blocks.agent.execute`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `task` | 필수 | `string` | 수행할 작업 설명 |
| `tools` | 선택적 | `array` | 사용 가능한 도구 정의 |
| `model` | 선택적 | `string` | 사용 모델. 기본 `"default"` |
| `system_prompt` | 선택적 | `string` | 시스템 프롬프트 |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `execution_id` | `string` | 실행 ID |
| `status` | `string` | 실행 상태 |
| `steps` | `array` | 실행 단계 목록 |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`task`이 지정되지 않음 |

---

### POST /api/agent/{id}/approve

에이전트의 현재 단계를 승인합니다. 내부에서 `blocks.agent.approve`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | execution_id |

**Response (`data`):** 승인 결과 개체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`execution_id`이 지정되지 않거나 실행되지 않음 |

---

### POST /api/agent/{id}/reject

에이전트의 현재 단계를 거부합니다. 내부에서 `blocks.agent.reject`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | execution_id |

**Response (`data`):** 거부 결과 개체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`execution_id`이 지정되지 않거나 실행되지 않음 |

---

### POST /api/agent/{id}/cancel

에이전트 실행을 취소합니다. 내부에서 `blocks.agent.cancel`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | execution_id |

**Response (`data`):** 취소 결과 개체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`execution_id`이 지정되지 않거나 실행되지 않음 |

---

### GET /api/agent/{id}/status

에이전트의 실행 상태를 취득한다. 내부에서 `blocks.agent.status`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | execution_id |

**Response (`data`):** 상태 객체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`execution_id`이 지정되지 않거나 실행되지 않음 |

---

### POST /api/agent/{id}/instruct

실행 중인 에이전트에 런타임 표시를 추가합니다. 내부에서 `blocks.agent.add_instruction`를 호출합니다. 표시는 다음 AI completion 단계 전에 메시지 기록에 주입됩니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | execution_id(경로에서 `execution_id`로 주입) |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `instruction` | 필수 | `string` | 추가 지침 |
| `priority` | 선택 | `string` | `"normal"` 또는 `"urgent"`. 기본 `"normal"` |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `instruction_id` | `string` | 지시 ID(UUID) |
| `execution_id` | `string` | 실행 ID |
| `priority` | `string` | 우선 순위 |
| `status` | `string` | `"queued"` |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`execution_id`이 지정되지 않음, `instruction`가 지정되지 않음, 실행이 존재하지 않거나 실행이 활성 상태가 아닙니다 |

---

## Multi-Agent — 멀티 에이전트 실행

### POST /api/agent/multi/execute

멀티 에이전트 세션을 시작합니다. 내부에서 `blocks.agent.multi_execute`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `task` | 필수 | `string` | 작업 설명 |
| `agents` | 필수 | `array[object]` | 에이전트 정의 목록(최소 하나). 각 요소는 `{name, role, model?, system_prompt?, tools?}` |
| `orchestration` | 선택적 | `string` | `"round_robin"`, `"directed"`, `"free"` 중 하나. 기본 `"round_robin"` |
| `max_turns` | 선택적 | `int` | 최대 턴 수. 기본 `10`. 하나 이상의 양의 정수 |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `session_id` | `string` | 세션 ID(`multi_` 접두사) |
| `status` | `string` | 세션 상태(`"completed"`, `"error"` 등) |
| `turn_results` | `array` | 각 턴의 결과 `[{agent, type, content}, ...]` |
| `result` | `object` | 세션 상세 개체 |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`task`이 지정되지 않음, `agents`가 지정되지 않거나 비어 있고 에이전트 정의의 `name`/`role`가 지정되지 않음, `orchestration`가 잘못된 값, `max_turns`가 양의 정수가 아닙니다 |

---

### GET /api/agent/multi/{id}/status

멀티 에이전트 세션의 상태를 얻는다. 내부에서 `blocks.agent.multi_status`를 호출합니다. 경로 매개 변수 `{id}`이 `session_id`로 주입됩니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | session_id |

**Response(`data`):** 세션 상태 개체(`session.to_dict()` 결과)

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`session_id`이 지정되지 않았거나 세션이 존재하지 않음 |

---

### POST /api/agent/multi/{id}/message

실행중인 멀티 에이전트 세션에 외부에서 메시지를 제출합니다. 내부에서 `blocks.agent.multi_message`를 호출합니다. 경로 매개 변수 `{id}`이 `session_id`로 주입됩니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | session_id |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `message` | 필수 | `string` | 입력할 메시지 내용 |
| `target_agent` | 선택적 | `string` | 특정 상담원에게 지정할 이름. 지정되지 않은 경우 공유 메시지로 모든 에이전트로 전송 |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `session_id` | `string` | 세션 ID |
| `message` | `string` | `"Message injected successfully"` |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` |`session_id`이 지정되지 않았거나 `message`가 지정되지 않았거나 세션이 존재하지 않음 |

---

## Consent — 동의 관리

### POST /api/consent/check

텍스트가 민감한지 여부를 결정합니다. 내부에서 `blocks.tool.consent_check`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `text` | 필수 | `string` | 판정 대상 텍스트 |
| `use_ai` | 선택 사항 | `bool` | AI 판정을 사용합니까? 기본 `false` |
| `model` | 선택 | `string` | AI 판정시 모델 지정. 기본 `"stub/default"` |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `requires_consent` | `bool` | 동의가 필요한지 |
| `categories` | `array[string]` | 감지된 카테고리 |
| `consent_id` | `string \| null` | 동의가 필요한 경우 동의 ID |
| `disclaimers` | `object` | 범주별 책임 텍스트 `{category: disclaimer_text}` |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `MISSING_PARAM` |`text`이 지정되지 않음 |
| `INVALID_PARAM` | `text`이 문자열이 아닙니다 |

---

### POST /api/consent/{id}/confirm

동의 또는 거부를 기록한다. 내부에서 `blocks.tool.consent_confirm`를 호출합니다. 경로 매개 변수 `{id}`이 `consent_id`로 주입됩니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `id` | 필수 | `string` | consent_id |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `accepted` | 필수 | `bool` | 사용자가 동의했는지 |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `consent_id` | `string` | 동의 ID |
| `accepted` | `bool` | 동의 상태 |
| `accepted_at` | `string \| null` | 동의한 경우 ISO 8601 타임스탬프 |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `MISSING_PARAM` |`consent_id` 또는 `accepted`가 지정되지 않음 |
| `INVALID_PARAM` |`consent_id`이 문자열이 아니거나 `accepted`가 bool이 아닙니다 |
| `NOT_FOUND` | 지정된 consent_id가 존재하지 않습니다 |

---

## Prompt — 프롬프트 관리

### PUT /api/prompts/{name}

기존 프롬프트를 업데이트합니다. 내부에서 `blocks.prompt.update`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `name` | 필수 | `string` | 프롬프트 이름 |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `content` | 선택적 | `string` | 새로운 본문(`body`의 별칭) |
| `body` | 선택적 | `string` | 새로운 본문 |
| `description` | 선택적 | `string` | 설명 |
| `variables` | 선택적 | `array` | 변수 정의 |
| `metadata` | 선택적 | `object` | 메타데이터 |

**Response (`data`):** 업데이트 후 프롬프트 개체

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 프롬프트가 존재하지 않습니다 |

---

### DELETE /api/prompts/{name}

프롬프트를 삭제합니다. 내부에서 `blocks.prompt.delete`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `name` | 필수 | `string` | 프롬프트 이름 |

**Response (`data`):** `{"deleted": true}`

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 프롬프트가 존재하지 않습니다 |

---

### POST /api/prompts/convert

tool ↔ prompt를 상호 변환합니다. 내부에서 `blocks.prompt.convert`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `source_type` | 필수 | `string` | `"tool"` 또는 `"prompt"` |
| `source_name` | 필수 | `string` | 변환 소스 이름 |
| `target_type` | 필수 | `string` | `"tool"` 또는 `"prompt"` |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `result` | `object` | 변환 결과(tool 정의 또는 프롬프트 객체) |
| `target_type` | `string` | 대상 유형 |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `INVALID_INPUT` |`source_type`/`target_type`가 잘못되었거나 동일합니다.
| `NOT_FOUND` | 변환 소스가 없습니다 |

---

## Tool — 동적 도구 관리

### POST /api/tools/create

동적 도구를 만듭니다. handler_code가 지정되지 않으면 AI로 자동 생성됩니다. 내부에서 `blocks.tool.create`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `name` | 필수 | `string` | 도구 이름(tool_id와 동일) |
| `description` | 선택 사항 | `string` | 도구 설명 |
| `parameters` | 필수 | `object` | JSON Schema 형식의 매개 변수 정의 |
| `handler_code` | 선택적 | `string` | Python handler 코드. null이면 AI 생성 |
| `tags` | 선택적 | `array[string]` | 태그. 기본 `["dynamic", "user-created"]` |
| `model` | 선택적 | `string` | handler_code 생성에 사용되는 AI 모델 |

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `tool_id` | `string` | 도구 ID |
| `name` | `string` | 도구 이름 |
| `summary` | `string` | 설명 |
| `handler_code` | `string` | 생성된 핸들러 코드 |
| `created_at` | `string` | ISO 8601 타임스탬프 |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `MISSING_PARAM` |`name` 또는 `parameters`가 지정되지 않음 |
| `INVALID_PARAM` | `parameters`이 dict가 아님 |
| `ALREADY_EXISTS` | 같은 이름의 도구가 이미 있습니다 |
| `REGISTER_ERROR` | 등록 과정에서 오류 |

---

### PUT /api/tools/{name}

동적 도구를 업데이트합니다. 내부에서 `blocks.tool.update`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `name` | 필수 | `string` | 도구 이름 |

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `description` | 선택적 | `string` | 새로운 설명 |
| `parameters` | 선택적 | `object` | 새로운 스키마 |
| `handler_code` | 선택적 | `string` | 새로운 핸들러 코드 |
| `tags` | 선택 사항 | `array[string]` | 새 태그 |

**Response (`data`):** 업데이트 후 도구 정의

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 도구가 없거나 dynamic이 아닙니다 |

---

### DELETE /api/tools/{name}

동적 도구를 삭제합니다. 파일도 동시에 삭제된다. 내부에서 `blocks.tool.delete`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `name` | 필수 | `string` | 도구 이름 |

**Response (`data`):** `{"deleted": true}`

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 도구가 없거나 dynamic이 아닙니다 |

---

### GET /api/tools/{name}/export

도구 정의를 handler_code로 내보냅니다. 내부에서 `blocks.tool.export`를 호출합니다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `name` | 필수 | `string` | 도구 이름 |

**Response(`data`):** 도구 정의 객체(handler_code 필드 포함)

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 도구가 없습니다 |

---

## Dev — 개발자 도구

### GET /api/dev/inspect

직전의 요구 정보를 취득한다. 내부에서 `blocks.dev.inspect`를 호출합니다.

**Request Body(선택 사항):**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `request_id` | 선택적 | `string` | 특정 요청 ID |
| `conversation_id` | 선택적 | `string` | 특정 대화 ID |

`request_id` 지정시에는 그 로그를 돌려준다. `conversation_id` 지정시 대화의 최신 로그를 반환합니다. 둘 다 지정되지 않은 직전의 요청을 반환합니다.

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `request_id` | `string` | 요청 ID |
| `conversation_id` | `string` | 대화 ID |
| `model` | `string` | 사용 모델 |
| `prompt_used` | `string` | 사용된 프롬프트 |
| `tools_called` | `array` | 호출된 도구 |
| `context_info` | `object` | 컨텍스트 정보 |
| `timestamp` | `string` | ISO 8601 타임스탬프 |

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 ID에 대한 로그가 없습니다 |

---

### GET /api/dev/prompt-history

프롬프트 기록을 얻습니다. 내부에서 `blocks.dev.prompt_history`를 호출합니다.

**Request Body(선택 사항):**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `limit` | 선택 | `int` | 취득 건수. 기본 20 |

**Response (`data`):** 로그 배열(새 순서)

---

### POST /api/dev/edit-prompt

프롬프트를 라이브 편집하고 다시 실행합니다. 내부에서 `blocks.dev.edit_prompt_live`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `request_id` | 필수 | `string` | 편집할 요청 ID |
| `new_prompt` | 필수 | `string` | 새로운 프롬프트 |

**Response (`data`):** 재실행 결과

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 요청이 없습니다 |
| `INVALID_INPUT` | 필수 매개변수 부족 |

---

### POST /api/dev/replay

과거 요청을 다시 실행합니다. 내부에서 `blocks.dev.replay`를 호출합니다.

**Request Body:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `request_id` | 필수 | `string` | 재실행 대상 요청 ID |
| `model` | 선택적 | `string` | 다른 모델에서 재실행 |

**Response (`data`):** 재실행 결과

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `NOT_FOUND` | 지정된 요청이 없습니다 |

---

## System — 시스템 정보

### GET /api/health

건강 확인. block를 호출하지 않고 직접 응답을 반환합니다.

**Request Body:** 없음

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `status` | `string` | `"healthy"` |
| `pack` | `string` | `"defaults"` |
| `ts` | `string` | ISO 8601 타임스탬프 |

**오류 케이스:** 없음

---

### GET /api/context

Pack의 컨텍스트 정보를 가져옵니다. facade 가 설정되어 있는 경우는 인터페이스 리스트도 돌려준다.

**Request Body:** 없음

**Response (`data`):**

| 필드 | 유형 | 설명 |
|---|---|---|
| `pack` | `string` | `"defaults"` |
| `interfaces` | `object` | 커널 외관 인터페이스 목록 |
| `ts` | `string` | ISO 8601 타임스탬프 |

**오류 케이스:** 없음

---

## Static — 정적 파일 전달

### GET /

Shell HTML을 반환합니다. `ui/shell.html`이 있으면 그 내용을 반환한다. 존재하지 않으면 폴백 HTML을 반환합니다.

**Response:** `text/html` 콘텐츠

---

### GET /static/{path}

정적 파일을 전달합니다. `..`에 의한 상위 디렉토리 참조는 차단된다.

**경로 매개변수:**

| 매개변수 | 필수 | 유형 | 설명 |
|---|---|---|---|
| `path` | 필수 | `string` | 파일의 상대 경로 |

**Response:** 해당 Content-Type의 파일 내용입니다. 바이너리 파일은 base64로 인코딩됩니다.

해당 확장자: `.html`, `.css`, `.js`, `.json`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.ico`

**오류 케이스:**

| 코드 | 설명 |
|---|---|
| `ERROR` | 경로가 잘못되었습니다 (`..` 포함) 또는 파일이 없습니다 |
