<!-- docs-i18n-links:start -->
[EN](../../chat.md) | [JP](../ja/chat.md) | [KR](./chat.md) | [CN](../zh-cn/chat.md)
<!-- docs-i18n-links:end -->

# Chat API

defaults Pack의 채팅 기능에 대한 모든 API 참조입니다. handler는 `blocks/chat/`에, 도메인 로직은 `domain/chat/store.py`(ChatStore)에 구현되어 있습니다.

ecosystem.json의 chat 구성 요소는 18 개의 handler를 제공합니다 : `create_conversation`, `get_conversation`, `list_conversations`, `update_conversation`, `delete_conversation`, `export_conversation`, `send`, `stream`, `add_message`, §RUMI§1 `branch`, `search`, `stop`, `regenerate`, `summarize_and_trim`, `auto_trim`.

## 제공자에 구애받지 않는 채팅 파이프라인

ChatStore는 공급자에 구애받지 않는 진실의 소스로 남아 있습니다. 저장된 루미 메시지는
공급자 계획 전에 Rumi Chat IR v2로 변환되었습니다. 유산
`convert_to_standard()` API는 호출 가능한 상태로 유지되며 여전히 기록을 반환합니다.
기존 공급자 어댑터에서 사용하는 StandardMessage 목록입니다.

런타임 흐름은 다음과 같습니다.

```text
ChatStore messages
  -> Rumi Chat IR v2
  -> Provider Capability Registry
  -> Request Planner / degradation metadata
  -> legacy StandardMessage or Provider Compiler v2
  -> provider response parser
  -> assistant RumiMessage
```

`PreparedChatRun`는 이제 `chat_ir`, `ir_schema_version`,
기존 `provider_capabilities` 및 `provider_planning`
§루미§0§. 보조 메타데이터는 IR 버전, 모델 라우팅,
채팅 참조, 계획 경고, 삭제된 기능 및 공급자 추적 정보.

롤백 플래그:

- `RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`: 유산 강제
  StandardMessage 공급자 경로입니다.
- `RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1`: Provider Compiler v2를 선택합니다.
  완전한 통화를 지원합니다.

공급자 추적 아티팩트는 다음 위치에 기록됩니다.
§루미§0§.
여기에는 수정된 기능, 계획, 페이로드 및 응답 요약이 포함됩니다.

## 외부 입력 대화

외부 공급자는 원시 공급자 페이로드를 사용하여 채팅 내부를 호출해서는 안 됩니다.
웹훅 및 게이트웨이 인테이크는 먼저 `ExternalEvent`를 생성하고 통과해야 합니다.
`AudiencePolicy`, `InputProfile`을 선택하고 `submit_input`를 호출합니다. 채팅
그러면 레이어는 외부 메타데이터가 첨부된 일반 사용자 메시지를 수신합니다.

외부 대화는 `conversation_kind: "external"` 및 stable을 사용해야 합니다.
`slack:{team_id}:{channel_id}:{thread_id}`과 같은 세션 키 또는
§루미§0§. 응답은 다음에 의해 계획되어야 합니다.
`ResponsePlanner`이며 `ResponseAdapter`에 의해 전달됩니다. 채팅 핸들러는 다음과 같은 행위를 해서는 안 됩니다.
원시 공급자 토큰을 보유하거나 공급자 API 호출을 직접 구성합니다.

## 대화 만들기

**handler**: `defaults.chat.create_conversation`(`blocks/chat/create_conversation.py`)

**HTTP**: `POST /api/chat/conversations`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `model` | `string` | 아니오 | AI 모델 이름. 기본 `"stub/default"` |
| `system_prompt_id` | `string` | 아니오 | 시스템 프롬프트 ID |
| `agent_id` | `string` | 아니오 | 에이전트 ID |
| `tags` | `string[]` | No | 태그 배열. 기본 `[]` |

**반환값**(`ok(conv)`):

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

## 대화 얻기

**handler**: `defaults.chat.get_conversation`(`blocks/chat/get_conversation.py`)

**HTTP**: `GET /api/chat/conversations/{id}`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID(URL 경로에서 자동 주입) |

**반환값**: `ok(conv)` — 전체 대화 객체(messages 포함). 찾을 수 없는 경우 `error("Conversation not found", "NOT_FOUND")`.

## 대화 목록

**handler**: `defaults.chat.list_conversations`(`blocks/chat/list_conversations.py`)

**HTTP**: `GET /api/chat/conversations`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `limit` | `int` | 아니오 | 취득 건수. 기본 `50` |
| `offset` | `int` | 아니오 | 오프셋. 기본 `0` |
| `tag` | `string` | 아니오 | 태그로 필터 |
| `is_starred` | `bool` | No | 스타 상태에서 필터 |
| `is_archived` | `bool` | 아니오 | 아카이브 상태의 필터 |

**반환값**: `ok({"conversations": [...], "total": int})`. `updated_at` 내림차순으로 정렬됩니다.

## 대화 업데이트

**handler**: `defaults.chat.update_conversation`(`blocks/chat/update_conversation.py`)

**HTTP**: `PUT /api/chat/conversations/{id}`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID(URL 경로에서 자동 주입) |
| `updates` | `dict` | Yes | 업데이트할 필드. `id`, `created_at`, `messages` 변경 불가 |

**반환값**: `ok(conv)` — 업데이트 후 대화 객체입니다.

## 대화 삭제

**handler**: `defaults.chat.delete_conversation`(`blocks/chat/delete_conversation.py`)

**HTTP**: `DELETE /api/chat/conversations/{id}`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID(URL 경로에서 자동 주입) |

**반환값**: `ok({"success": true})`. 찾을 수 없는 경우 `error("Conversation not found", "NOT_FOUND")`.

## 메시지 보내기(AI 응답 포함)

**handler**: `defaults.chat.send`(`blocks/chat/send.py`)

**HTTP**: `POST /api/chat/conversations/{id}/messages` 또는 `POST /v1/chat/completions`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `message` | `dict` | Yes | 메시지 개체 |
| `message.role` | `string` | 아니오 | 역할. 기본 `"user"` |
| `message.content` | `string` or `list` | Yes | 메시지 내용. 문자열의 경우 `[{"type": "text", "text": ...}]`로 변환됩니다.

**처리 흐름**: 사용자 메시지를 `ChatStore.add_message()` 에서 저장 → `get_message_chain()` 에서 대화 이력 얻기 → `convert_to_standard()` 에서 표준 형식으로 변환 → `call_handler("defaults.ai.complete", ...)` 에서 AI 호출 → `build_assistant_message()` 에서 assistant 메시지를 구축 → `ChatStore.add_message()` 로 저장.

**반환값**: `ok(assistant_msg)` — AI 응답 메시지 객체.

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

## 메시지 추가(AI 응답 없음)

**handler**: `defaults.chat.add_message`(`blocks/chat/add_message.py`)

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `message` | `dict` | Yes | 메시지 객체(role, content) |

**반환값**: `ok(msg)` — 추가된 메시지 객체입니다. AI 호출은 발생하지 않습니다.

## 메시지 얻기

**handler**: `defaults.chat.get_message`(`blocks/chat/get_message.py`)

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `message_id` | `string` | Yes | 메시지 ID |

**반환값**: `ok(msg)` — 메시지 객체.

## 메시지 업데이트

**handler**: `defaults.chat.update_message`(`blocks/chat/update_message.py`)

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `message_id` | `string` | Yes | 메시지 ID |
| `updates` | `dict` | Yes | 업데이트할 필드. `id`, `conversation_id`, `created_at` 변경 불가 |

**반환값**: `ok(msg)` — 갱신 후의 메시지 오브젝트.

## 메시지 삭제

**handler**: `defaults.chat.delete_message`(`blocks/chat/delete_message.py`)

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `message_id` | `string` | Yes | 메시지 ID |

**반환값**: `ok({"success": true})`. 상위 메시지의 `children_ids`에서 자동으로 삭제됩니다. `current_node_id`가 삭제 대상이면 `parent_id`로 업데이트됩니다.

## 스트리밍 전송

**handler**: `defaults.chat.stream`(`blocks/chat/stream.py`)

**HTTP**: `POST /api/chat/conversations/{id}/stream`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `message` | `dict` | Yes | 메시지 개체 |

**처리**: 사용자 메시지를 저장하고 `call_handler("defaults.ai.stream", ...)`에서 스트리밍 AI 호출을 수행합니다. `stream_id`이 반환되며 스트림을 중지할 수 있습니다.

**반환값**: `ok({"stream_id": "...", "conversation_id": "..."})`

## 스트리밍 중지

**handler**: `defaults.chat.stop`(`blocks/chat/stop.py`)

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `stream_id` | `string` | 아니오 | 중지할 스트림 ID |

**반환값**: `ok({"success": true})`

## AI 응답 재생성

**handler**: `defaults.chat.regenerate`(`blocks/chat/regenerate.py`)

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `message_id` | `string` | Yes | 재생성 대상 메시지 ID |

**처리**: 지정된 메시지 삭제 → 상위 메시지까지 대화 체인 가져오기 → AI로 다시 보내기 → 새 assistant 메시지를 저장합니다.

**반환값**: `ok(assistant_msg)` — 새로운 AI 응답 메시지.

## 브랜치(대화 분기)

**handler**: `defaults.chat.branch`(`blocks/chat/branch.py`)

**HTTP**: 직접 HTTP 경로는 정의되지 않았습니다. `call_handler("defaults.chat.branch", ...)`를 통해 호출합니다.

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | 예 | 원래 대화 ID |
| `message_id` | `string` | Yes | 분기점의 메시지 ID |

**처리**: `ChatStore.branch()`가 지정된 메시지까지 체인을 복사하여 새 대화를 만듭니다. 새 대화 제목에는 `" (branch)"`이 추가됩니다. 메시지의 `parent_id` / `children_ids`는 새 ID로 다시 매핑됩니다.

**반환값**: `ok(new_conv)` — 새로 분기된 대화 객체입니다.

## 검색

**handler**: `defaults.chat.search`(`blocks/chat/search.py`)

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `query` | `string` | Yes | 검색 쿼리 |
| `conversation_id` | `string` | 아니오 | 특정 대화 내로 제한하는 경우 |

**처리**: `ChatStore.search()`가 모든 메시지의 `raw_text` 필드에 대해 대소문자를 구분하지 않는 부분 일치 검색을 수행합니다.

**반환값**: `ok({"results": [msg, msg, ...]})`

## 내보내기

**handler**: `defaults.chat.export_conversation`(`blocks/chat/export_conversation.py`)

**HTTP**: `POST /api/chat/conversations/{id}/export`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `format` | `string` | 아니오 | `"markdown"` 또는 `"json"`. 기본 `"markdown"` |

**반환값**: `ok({"content": "..."})`. `domain/chat/exporter.py`의 `export_markdown()` 또는 `export_json()`가 호출됩니다.

## 대화 기록의 AI 요약(summarize_and_trim)

**handler**: `defaults.chat.summarize_and_trim`(`blocks/chat/summarize_and_trim.py`)

**HTTP**: `POST /api/chat/conversations/{id}/summarize`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `start_message_id` | `string` | Yes | 요약 범위 시작 메시지 ID |
| `end_message_id` | `string` | Yes | 요약 범위 종료 메시지 ID |
| `model` | `string` | 아니오 | 요약에 사용되는 AI 모델. `"default"`의 경우 대화 모델 사용 |
| `instruction` | `string` | 아니오 | 추가 요약 지침 |

**처리**: 지정된 범위의 메시지 가져오기 → `convert_to_standard()`에서 표준 형식으로 변환 → 요약 프롬프트 작성 → AI로 요약 → 범위 내 메시지 일괄 삭제(`delete_messages_bulk`) → 요약 메시지 삽입(`insert_message_at`). 요약 메시지의 `metadata`에는 `is_summary: true`와 `original_message_ids`가 포함됩니다.

**반환값**:

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

## 대화 기록의 AI 자동 트림 제안(auto_trim)

**handler**: `defaults.chat.auto_trim`(`blocks/chat/auto_trim.py`)

**HTTP**: `POST /api/chat/conversations/{id}/auto-trim`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `conversation_id` | `string` | Yes | 대화 ID |
| `model` | `string` | 아니오 | 분석에 사용되는 AI 모델. `"default"`의 경우 대화 모델 사용 |
| `max_context_tokens` | `int` | 아니오 | 트림 후 목표 토큰 수 |

**처리**: 대화의 모든 메시지 가져오기 → 각 메시지의 content에서 텍스트 추출 → AI로 분석 프롬프트 보내기 → AI가 요약할 수 있는 세그먼트를 JSON 배열로 반환 → 메시지 ID의 존재 확인으로 검증.

**반환값**:

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

반환 된 `segments`의 각 `start_id` / `end_id`를 `summarize_and_trim`에 전달하여 실제 트림을 수행 할 수 있습니다.

## 모든 API 엔드 포인트 목록

| 메소드 | 경로 | handler 파일 |
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
