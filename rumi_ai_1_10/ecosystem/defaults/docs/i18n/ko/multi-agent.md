<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](../ja/multi-agent.md) | [KR](./multi-agent.md) | [CN](../zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# Multi-Agent API

defaults Pack의 멀티 에이전트 기능에 대한 모든 API 참조입니다. handler는 `blocks/agent/multi_*.py`에, 도메인 로직은 `domain/agent/multi.py`(MultiAgentOrchestrator)에 구현되어 있습니다.

## 멀티 에이전트 개념

멀티 에이전트는 여러 AI 에이전트가 협력하여 작업을 수행하는 메커니즘입니다. 각 에이전트는 `AgentDefinition`(`domain/agent/agent_def.py`)에 정의되며 이름, 역할, 모델 시스템 프롬프트 도구를 갖습니다.

`MultiAgentOrchestrator`는 전체 세션을 관리하고 `MessageBus`(인메모리)를 통해 에이전트 간의 메시지 교환을 수행합니다. 각 에이전트에는 공유 메시지 기록과 개인 메시지 대기열이 있습니다.

상담원 응답에 `[DONE]` 마커가 포함되어 있으면 상담원이 완료 상태가 됩니다. 모든 에이전트가 완료되거나 최대 턴 수에 도달하면 세션이 완료됩니다.

에이전트는 응답 내에서 `@agent_name: message` 형식으로 다른 에이전트에 멘션할 수 있습니다. `directed` 오케스트레이션에서이 멘션은 다음 발언자를 결정하는 데 사용됩니다.

## 세션 생성(multi_execute)

**handler**: `defaults.agent.multi_execute`(`blocks/agent/multi_execute.py`)

**HTTP**: `POST /api/agent/multi/execute`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `task` | `string` | Yes | 작업 설명 |
| `agents` | `list[dict]` | Yes | 에이전트 정의 목록(최소 하나) |
| `orchestration` | `string` | No | `"round_robin"`, `"directed"`, `"free"` 중 하나. 기본 `"round_robin"` |
| `max_turns` | `int` | No | 최대 턴 수. 기본 `10`. 하나 이상의 양의 정수 |

## 에이전트 정의

`agents` 배열의 각 요소는 다음 필드를 가진 dict입니다.

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `name` | `string` | Yes | 상담원 이름(고유). 멘션 (`@name:`)에 사용 |
| `role` | `string` | 예 | 역할 설명 |
| `model` | `string` | No | AI 모델. 기본 `"default"` |
| `system_prompt` | `string` | 아니오 | 시스템 프롬프트 |
| `tools` | `list` | 아니오 | 사용 가능한 도구 정의 목록 |
| `agent_id` | `string` | 아니오 | 고유 식별자. 지정되지 않은 경우 자동 생성(`agentdef_`+UUID) |

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

**`round_robin`**(기본값): 상담원이 순서대로 발언합니다. `session.current_turn % len(agents)`에서 다음 발언자가 결정됩니다. 완료된(`done: true`) 에이전트는 건너뜁니다.

**`directed`**: 마지막 메시지의 `@agent_name:` 멘션에서 다음 발언자를 결정합니다. 멘션이 없으면 라운드 로빈으로 폴백합니다. `_MENTION_RE = re.compile(r"@(\w+)\s*:")`로 구문 분석됩니다.

**`free`**: 모든 미완료 에이전트가 병렬로 발언합니다. `threading.Thread`를 사용하여 여러 에이전트의 턴을 동시에 실행합니다. 각 스레드의 시간 초과는 120초입니다.

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

**handler**: `defaults.agent.multi_status`(`blocks/agent/multi_status.py`)

**HTTP**: `GET /api/agent/multi/{id}/status`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `session_id` | `string` | Yes | 세션 ID(URL 경로에서 자동 주입) |

**처리**: `_state.get_multi_session(session_id)`에서 세션을 가져오고 `orchestrator.get_status(session)`에서 `session.to_dict()`를 반환합니다.

**반환값**: `ok(session_dict)` — 세션의 완전한 상태.

**오류 사례**: `session_id`가 지정되지 않았거나 세션이 없는 경우 `error(...)`를 반환합니다.

## 외부로부터의 메시지 투입

**handler**: `defaults.agent.multi_message`(`blocks/agent/multi_message.py`)

**HTTP**: `POST /api/agent/multi/{id}/message`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `session_id` | `string` | Yes | 세션 ID(URL 경로에서 자동 주입) |
| `message` | `string` | Yes | 입력할 메시지 내용 |
| `target_agent` | `string` | 아니오 | 특정 상담원을 대상으로 하는 이름 |

**처리**: `target_agent`가 지정되면 `post_direct("user", target, message, turn)`에서 직접 메시지를 보내고 해당 에이전트의 `agent_contexts[name]["messages"]`에도 `[User message]: ...`로 추가합니다. 지정되지 않은 경우 `post_shared("user", message, turn)`에서 공유 메시지로 게시하여 모든 에이전트의 메시지에 추가합니다.

**반환값**: `ok({"session_id": "...", "message": "Message injected successfully"})`

**오류 사례**: `session_id`이 지정되지 않았거나 `message`가 지정되지 않았거나 세션이 없으면 `error(...)`를 반환합니다.

## 모든 HTTP 엔드 포인트 목록

| 메소드 | 경로 | handler 파일 | 주입되는 경로 매개변수 |
|---|---|---|---|
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` | — |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` | `{id}` → `session_id` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` | `{id}` → `session_id` |
