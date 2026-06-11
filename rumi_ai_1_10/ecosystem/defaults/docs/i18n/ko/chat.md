<!-- docs-i18n-links:start -->
[EN](../../chat.md) | [JP](../ja/chat.md) | [KR](./chat.md) | [CN](../zh-cn/chat.md)
<!-- docs-i18n-links:end -->

# 채팅 API

기본 팩의 채팅 기능에 대한 전체 API 참조입니다. 핸들러는 `blocks/chat/`에서 구현되고 도메인 로직은 `domain/chat/store.py`(ChatStore)에서 구현됩니다.

Ecosystem.json의 채팅 구성 요소는 18개의 처리기를 제공합니다: `create_conversation`, `get_conversation`, `list_conversations`, `update_conversation`, `delete_conversation`, `export_conversation`, `send`, `stream`, `add_message`, `get_message`, `update_message`, `delete_message`, `branch`, `search`, `stop`, `regenerate`, `summarize_and_trim`, `auto_trim`.

## 대화 만들기

**처리기**: `defaults.chat.create_conversation`(`blocks/chat/create_conversation.py`)**HTTP**: `POST /api/chat/conversations`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | `string` | No | AI model name. Default `"stub/default"` |
| `system_prompt_id` | `string` | No | System Prompt ID |
| `agent_id` | `string` | No | Agent ID |
| `tags` | `string[]` | No | Tag array. Default `[]` |

**반환 값**(`ok(conv)`):

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

## 대화를 시작하세요

**처리기**: `defaults.chat.get_conversation`(`blocks/chat/get_conversation.py`)**HTTP**: `GET /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |

**반환 값**: `ok(conv)` — 전체 대화 개체(메시지 포함). 찾을 수 없는 경우 `error("Conversation not found", "NOT_FOUND")`.

## 대화 목록

**처리기**: `defaults.chat.list_conversations`(`blocks/chat/list_conversations.py`)**HTTP**: `GET /api/chat/conversations`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `limit` | `int` | No | Number of acquisitions. Default `50` |
| `offset` | `int` | No | Offset. Default `0` |
| `tag` | `string` | No | Filter by tag |
| `is_starred` | `bool` | No | Filter by star status |
| `is_archived` | `bool` | No | Filter by archive status |

**반환 값**: `ok({"conversations": [...], "total": int})`. `updated_at` 내림차순으로 정렬됩니다.

## 대화 업데이트

**처리기**: `defaults.chat.update_conversation`(`blocks/chat/update_conversation.py`)**HTTP**: `PUT /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update. `id`, `created_at`, `messages` cannot be changed |

**반환 값**: `ok(conv)` — 업데이트된 대화 개체.

## 대화 삭제

**처리기**: `defaults.chat.delete_conversation`(`blocks/chat/delete_conversation.py`)**HTTP**: `DELETE /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |

**반환 값**: `ok({"success": true})`. 찾을 수 없는 경우 `error("Conversation not found", "NOT_FOUND")`.

## 메시지 보내기(AI 응답 포함)

**처리기**: `defaults.chat.send`(`blocks/chat/send.py`)**HTTP**: `POST /api/chat/conversations/{id}/messages` 또는 `POST /v1/chat/completions`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object |
| `message.role` | `string` | No | Role. Default `"user"` |
| `message.content` | `string` or `list` | Yes | Message content. If it is a string, it will be converted to `[{"type": "text", "text": ...}]` |

**처리 흐름**: `ChatStore.add_message()`에 사용자 메시지 저장 → `get_message_chain()`에서 대화 기록 가져오기 → `convert_to_standard()`에서 표준 형식으로 변환 → `call_handler("defaults.ai.complete", ...)`에서 AI 호출 → `build_assistant_message()`에서 보조 메시지 작성 → `ChatStore.add_message()`에 저장.**반환 값**: `ok(assistant_msg)` — AI 응답 메시지 객체.

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

## 메시지 추가(AI 무응답)

**처리자**: `defaults.chat.add_message`(`blocks/chat/add_message.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object (role, content) |

**반환 값**: `ok(msg)` — 메시지 개체가 추가되었습니다. AI 호출은 이루어지지 않습니다.

## 메시지 받기

**처리자**: `defaults.chat.get_message`(`blocks/chat/get_message.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |

**반환 값**: `ok(msg)` — 메시지 개체.

## 업데이트 메시지

**처리자**: `defaults.chat.update_message`(`blocks/chat/update_message.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |
| `updates` | `dict` | Yes | Field to update. `id`, `conversation_id`, `created_at` cannot be changed |

**반환 값**: `ok(msg)` — 메시지 개체가 업데이트되었습니다.

## 메시지 삭제

**처리자**: `defaults.chat.delete_message`(`blocks/chat/delete_message.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |

**반환 값**: `ok({"success": true})`. 상위 메시지의 `children_ids`에서 자동으로 제거됩니다. `current_node_id`가 삭제 대상인 경우 `parent_id`로 업데이트됩니다.

## 스트리밍 전송

**처리기**: `defaults.chat.stream`(`blocks/chat/stream.py`)**HTTP**: `POST /api/chat/conversations/{id}/stream`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object |

**처리**: `call_handler("defaults.ai.stream", ...)`에서 사용자 메시지를 저장하고 스트리밍 AI 호출을 수행합니다. `stream_id`이 반환되며 스트림을 중지하는 데 사용할 수 있습니다.**반환 값**: `ok({"stream_id": "...", "conversation_id": "..."})`

## 스트리밍 중지

**처리자**: `defaults.chat.stop`(`blocks/chat/stop.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `stream_id` | `string` | No | ID of the stream to stop |

**반환 값**: `ok({"success": true})`

## AI 응답 재생성

**처리자**: `defaults.chat.regenerate`(`blocks/chat/regenerate.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID to be regenerated |

**처리 중**: 지정된 메시지 삭제 → 상위 메시지까지 대화 체인 가져오기 → AI로 다시 보내기 → 새 보조 메시지 저장.**반환 값**: `ok(assistant_msg)` — 새 AI 응답 메시지.

## 분기(대화 분기)

**핸들러**: `defaults.chat.branch`(`blocks/chat/branch.py`)**HTTP**: 직접 HTTP 경로가 정의되지 않았습니다. `call_handler("defaults.chat.branch", ...)`.**input_data**를 통해 호출:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Original conversation ID |
| `message_id` | `string` | Yes | Branch origin message ID |

**처리 중**: `ChatStore.branch()`은 지정된 메시지까지 체인을 복사하여 새 대화를 만듭니다. 새로운 대화 제목에는 `" (branch)"`이 추가됩니다. 메시지의 `parent_id` / `children_ids`가 새 ID로 다시 매핑됩니다.**반환 값**: `ok(new_conv)` — 새로운 분기된 대화 개체입니다.

## 검색

**처리자**: `defaults.chat.search`(`blocks/chat/search.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | Search query |
| `conversation_id` | `string` | No | To limit to a specific conversation |

**처리 중**: `ChatStore.search()`은 모든 메시지의 `raw_text` 필드에 대해 대소문자를 구분하지 않는 부분 일치 검색을 수행합니다.**반환 값**: `ok({"results": [msg, msg, ...]})`

## 내보내기

**처리기**: `defaults.chat.export_conversation`(`blocks/chat/export_conversation.py`)**HTTP**: `POST /api/chat/conversations/{id}/export`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `format` | `string` | No | `"markdown"` or `"json"`. Default `"markdown"` |

**반환 값**: `ok({"content": "..."})`. `domain/chat/exporter.py`, `export_markdown()` 또는 `export_json()`이 호출됩니다.

## AI 대화 기록 요약(summarize_and_trim)

**처리기**: `defaults.chat.summarize_and_trim`(`blocks/chat/summarize_and_trim.py`)**HTTP**: `POST /api/chat/conversations/{id}/summarize`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `start_message_id` | `string` | Yes | Start message ID of summary range |
| `end_message_id` | `string` | Yes | End of summary range message ID |
| `model` | `string` | No | AI model used for summarization. Use conversational model for `"default"` |
| `instruction` | `string` | No | Additional summary instructions |

**처리 중**: 지정된 범위의 메시지 가져오기 → `convert_to_standard()`을 사용하여 표준 형식으로 변환 → 요약 프롬프트 작성 → AI 요약 허용 → 범위 내 메시지 일괄 삭제(`delete_messages_bulk`) → 요약 메시지 삽입(`insert_message_at`). 요약 메시지 `metadata`에는 `is_summary: true` 및 `original_message_ids`이 포함됩니다.**반환 값**:

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

## 대화내역 AI 자동 다듬기 제안(auto_trim)

**처리기**: `defaults.chat.auto_trim`(`blocks/chat/auto_trim.py`)**HTTP**: `POST /api/chat/conversations/{id}/auto-trim`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `model` | `string` | No | AI model used for analysis. Use conversational model for `"default"` |
| `max_context_tokens` | `int` | No | Target number of tokens after trimming |

**처리 중**: 대화의 모든 메시지 가져오기 → 각 메시지 내용에서 텍스트 추출 → AI에 분석 프롬프트 보내기 → AI가 요약 가능한 세그먼트를 JSON 배열로 반환 → 메시지 ID가 있는지 확인하여 유효성 검사**반환 값**:

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

실제 트리밍은 반환된 `segments`의 각 `start_id` / `end_id`을 `summarize_and_trim`에 전달하여 수행할 수 있습니다.

## 모든 API 엔드포인트 목록

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
