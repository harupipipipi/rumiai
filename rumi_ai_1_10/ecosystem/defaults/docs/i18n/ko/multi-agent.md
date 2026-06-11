<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](../ja/multi-agent.md) | [KR](./multi-agent.md) | [CN](../zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# 다중 에이전트 API

기본 팩의 다중 에이전트 기능에 대한 전체 API 참조입니다. 처리기는 `blocks/agent/multi_*.py`에서 구현되고 도메인 논리는 `domain/agent/multi.py`(MultiAgentOrchestrator)에서 구현됩니다.

## 다중 에이전트 개념

멀티 에이전트는 여러 AI 에이전트가 협력하여 작업을 수행하는 시스템입니다. 각 에이전트는 `AgentDefinition`(`domain/agent/agent_def.py`)에 정의되어 있으며 이름, 역할, 모델, 시스템 프롬프트 및 도구가 있습니다.

`MultiAgentOrchestrator`은 전체 세션을 관리하고 `MessageBus`(in-memory)을 통해 에이전트 간 메시지를 교환한다. 각 에이전트에는 공유 메시지 기록과 개인 메시지 대기열이 있습니다.

에이전트의 응답에 `[DONE]` 마커가 포함되어 있으면 에이전트는 완료된 상태입니다. 모든 에이전트가 완료되거나 최대 회전 수에 도달하면 세션이 종료됩니다.

상담원은 응답에서 `@agent_name: message` 형식으로 다른 상담원을 언급할 수 있습니다. `directed` 오케스트레이션에서는 이 언급을 사용하여 다음 발언자를 결정합니다.

## 세션 생성(multi_execute)

**처리기**: `defaults.agent.multi_execute`(`blocks/agent/multi_execute.py`)**HTTP**: `POST /api/agent/multi/execute`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `agents` | `list[dict]` | Yes | List of agent definitions (at least one) |
| `orchestration` | `string` | No | Any of `"round_robin"`, `"directed"`, `"free"`. Default `"round_robin"` |
| `max_turns` | `int` | No | Maximum number of turns. Default `10`. Positive integer greater than or equal to 1 |

## 에이전트 정의

`agents` 배열의 각 요소는 다음 필드가 포함된 사전입니다.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Agent name (unique). Used for mentions (`@name:`) |
| `role` | `string` | Yes | Role description |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |
| `tools` | `list` | No | Available tool definition list |
| `agent_id` | `string` | No | Unique identifier. Automatically generated if not specified (`agentdef_` + UUID) |

**input_data 예**:

```json
{
  "task": "Create a Python web scraper and review the code",
  "agents": [
    {
      "name": "coder",
      "role": "You are a senior Python developer. Write clean, efficient code.",
      "model": "openai/gpt-4o",
      "system_prompt": "Focus on writing production-quality Python code."
    },
    {
      "name": "reviewer",
      "role": "You are a code reviewer. Find bugs, suggest improvements.",
      "model": "openai/gpt-4o",
      "system_prompt": "Review code thoroughly for bugs, security issues, and best practices."
    }
  ],
  "orchestration": "round_robin",
  "max_turns": 6
}
```

## 오케스트레이션 방법

**`round_robin`**(기본값): 에이전트가 차례로 말합니다. `session.current_turn % len(agents)`에 따라 다음 발언자가 결정됩니다. 완료된(`done: true`) 에이전트는 건너뜁니다.**`directed`**: 이전 메시지의 `@agent_name:` 언급에서 다음 화자를 결정합니다. 언급이 없으면 라운드 로빈으로 돌아갑니다. `_MENTION_RE = re.compile(r"@(\w+)\s*:")`로 구문 분석되었습니다.

**`free`**: 불완전한 모든 에이전트는 동시에 말합니다. 여러 에이전트 턴을 동시에 실행하려면 `threading.Thread`을 사용하세요. 각 스레드의 시간 제한은 120초입니다.

## 반환 값

```json
{
  "status": "ok",
  "data": {
    "session_id": "multi_xxxxxxxx",
    "status": "completed",
    "turn_results": [
      {"agent": "coder", "type": "text", "content": "Here is the code..."},
      {"agent": "reviewer", "type": "text", "content": "@coder: Found a bug..."},
      {"agent": "coder", "type": "text", "content": "Fixed. [DONE]"},
      {"agent": "reviewer", "type": "text", "content": "Looks good. [DONE]"}
    ],
    "result": {
      "session_id": "multi_xxxxxxxx",
      "task": "...",
      "agents": [{"agent_id": "...", "name": "coder", "role": "...", "model": "...", "system_prompt": "...", "tools": []}],
      "orchestration": "round_robin",
      "max_turns": 6,
      "status": "completed",
      "current_turn": 4,
      "message_bus": {
        "shared_messages": [{"id": "msg_xxx", "sender": "coder", "content": "...", "turn": 1, "timestamp": "..."}],
        "private_queues": {"coder": [], "reviewer": []}
      },
      "agent_contexts": {
        "coder": {"status": "idle", "turns_taken": 2, "done": true, "message_count": 0},
        "reviewer": {"status": "idle", "turns_taken": 2, "done": true, "message_count": 0}
      },
      "shared_context": {},
      "result": "Looks good. [DONE]",
      "error": null,
      "created_at": "...",
      "updated_at": "..."
    }
  }
}
```

## 상태 확인

**처리기**: `defaults.agent.multi_status`(`blocks/agent/multi_status.py`)**HTTP**: `GET /api/agent/multi/{id}/status`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |

**처리 중**: `_state.get_multi_session(session_id)`에서 세션을 가져오고 `orchestrator.get_status(session)`에서 `session.to_dict()`을 반환합니다.**반환 값**: `ok(session_dict)` — 세션의 전체 상태.**오류 사례**: `session_id`가 지정되지 않거나 세션이 존재하지 않는 경우 `error(...)`를 반환합니다.

## 외부에서 메시지 입력하기

**처리기**: `defaults.agent.multi_message`(`blocks/agent/multi_message.py`)**HTTP**: `POST /api/agent/multi/{id}/message`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |
| `message` | `string` | Yes | Message content to be input |
| `target_agent` | `string` | No | Name when addressing to a specific agent |

**처리 중**: `target_agent`이 지정된 경우 `post_direct("user", target, message, turn)`을 포함하여 다이렉트 메시지를 보내고 상담원의 `agent_contexts[name]["messages"]`에도 `[User message]: ...`로 추가합니다. 지정하지 않으면 `post_shared("user", message, turn)`를 사용하여 공유 메시지로 게시되고 모든 에이전트의 메시지에 추가됩니다.**반환 값**: `ok({"session_id": "...", "message": "Message injected successfully"})`**오류 사례**: `session_id`이 지정되지 않거나, `message`이 지정되지 않거나, 세션이 존재하지 않는 경우 `error(...)`을 반환합니다.

## 모든 HTTP 엔드포인트 목록

| method | path | handler file | injected path parameter |
|---|---|---|---|
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` | — |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` | `{id}` → `session_id` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` | `{id}` → `session_id` |
