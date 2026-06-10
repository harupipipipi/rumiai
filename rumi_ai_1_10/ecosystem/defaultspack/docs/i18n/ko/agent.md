<!-- docs-i18n-links:start -->
[EN](../../agent.md) | [JP](../ja/agent.md) | [KR](./agent.md) | [CN](../zh-cn/agent.md)
<!-- docs-i18n-links:end -->

# Agent API

defaults Pack의 에이전트 기능에 대한 모든 API 참조입니다. handler는 `blocks/agent/`에, 도메인 로직은 `domain/agent/engine.py`(AgentEngine)과 `domain/agent/execution.py`(AgentExecution)에 구현되어 있습니다.

## 에이전트 개념

에이전트는 "작업을 받고, AI가 생각하고, 필요에 따라 도구를 호출하고 결과를 반환하는"실행 루프입니다. defaults Pack 에이전트는 다음 flow로 구현됩니다.

1. 사용자가 작업과 사용 가능한 도구를 지정하여 `execute`를 호출합니다.
2. `AgentEngine`가 초기 메시지(system_prompt + task)를 구축하여 AI로 전송한다.
3. AI가 "텍스트 응답"을 반환하는 경우 → 작업 완료(status: `completed`).
4. AI가 "도구 호출"을 반환하는 경우 → 사용자 승인 대기(status: `waiting_approval`).
5. 사용자가 `approve` → 도구 실행 → 결과를 AI로 반환 → 3으로 돌아갑니다.
6. 사용자가 §RUMI § 0 § → 거부 이유를 AI로 반환 → AI가 대안을 제안 → 3으로 돌아갑니다.
7. 도구 호출 깊이가 `MAX_FLOW_CALL_DEPTH`(10)에 도달한 경우 → 오류.

`blocks/agent/_state.py`이 메모리 내에서 실행 중인 `AgentEngine` 인스턴스를 관리합니다. `execution_id`를 키로 사용하여 `set_engine()` / `get_engine()` / `remove_engine()`에서 관리합니다.

## 태스크 실행(execute)

**handler**: `defaults.agent.execute`(`blocks/agent/execute.py`)

**HTTP**: `POST /api/agent/execute`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `task` | `string` | Yes | 작업 설명 |
| `tools` | `list` | No | 사용 가능한 도구 정의 목록. 기본 `[]` |
| `model` | `string` | No | AI 모델. 기본 `"default"` |
| `system_prompt` | `string` | 아니오 | 시스템 프롬프트 |

**처리**: `AgentEngine().execute(task, tools, model, system_prompt, context)`를 호출합니다. 초기 메시지를 작성하고 AI로 보내고 응답에 따라 `completed` / `waiting_approval` / `error`의 상태를 반환합니다.

**반환값**:

```json
{
  "status": "ok",
  "data": {
    "execution_id": "agent_xxxxxxxx",
    "status": "waiting_approval",
    "result": {
      "execution_id": "agent_xxxxxxxx",
      "task": "...",
      "tools": [],
      "model": "default",
      "system_prompt": "...",
      "status": "waiting_approval",
      "steps": [
        {"step_id": "step_xxx", "step_number": 1, "step_type": "think", "content": {"action": "start", "task": "..."}},
        {"step_id": "step_xxx", "step_number": 2, "step_type": "tool_call", "content": {"tool_name": "...", "tool_args": {}}}
      ],
      "current_step": 2,
      "result": null,
      "error": null,
      "pending_tool_call": {"tool_name": "...", "tool_args": {}, "raw": {}},
      "created_at": "...",
      "updated_at": "..."
    }
  }
}
```

## 승인(approve)

**handler**: `defaults.agent.approve`(`blocks/agent/approve.py`)

**HTTP**: `POST /api/agent/{id}/approve`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 실행 ID(URL 경로에서 자동 주입) |

**처리**: `engine.approve(execution_id)`를 호출합니다. 보류 중인 도구를 실행하고 결과를 AI로 반환하고 다음 응답을 얻습니다. AI가 추가 도구를 호출하면 다시 `waiting_approval`가 됩니다.

**반환값**: `ok(result)` — 업데이트된 실행 상태.

## 거부 (reject)

**handler**: `defaults.agent.reject`(`blocks/agent/reject.py`)

**HTTP**: `POST /api/agent/{id}/reject`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 실행 ID(URL 경로에서 자동 주입) |
| `reason` | `string` | 아니오 | 거부 이유. 기본 `"Rejected by user"` |

**처리**: `engine.reject(execution_id, reason)`를 호출합니다. "사용자가 도구 호출을 거부했습니다. 이유 : {reason}. 대안을 제안하십시오."라는 메시지를 AI에 보냅니다.

**반환값**: `ok(result)` — 업데이트된 실행 상태.

## 취소

**handler**: `defaults.agent.cancel`(`blocks/agent/cancel.py`)

**HTTP**: `POST /api/agent/{id}/cancel`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 실행 ID(URL 경로에서 자동 주입) |

**처리**: `engine.cancel(execution_id)`를 호출하고 `_state.remove_engine(execution_id)`에서 엔진을 메모리에서 제거합니다. `InstructionQueue`의 해당 실행 지시도 지워집니다.

**반환값**: `ok({"execution_id": "...", "status": "cancelled"})`

## 상태 확인

**handler**: `defaults.agent.status`(`blocks/agent/status.py`)

**HTTP**: `GET /api/agent/{id}/status`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 실행 ID(URL 경로에서 자동 주입) |

**반환값**:

```json
{
  "status": "ok",
  "data": {
    "execution_id": "agent_xxx",
    "status": "waiting_approval",
    "steps": [
      {"step_id": "...", "step_number": 1, "step_type": "think", "content": {...}, "status": "completed", "created_at": "..."},
      {"step_id": "...", "step_number": 2, "step_type": "tool_call", "content": {...}, "status": "pending", "created_at": "..."}
    ],
    "current_step": 2
  }
}
```

## 계획 전용(plan)

**handler**: `defaults.agent.plan`(`blocks/agent/plan.py`)

현재 HTTP 루트는 정의되지 않았습니다. `call_handler("defaults.agent.plan", ...)`를 통해서만 호출 가능.

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `task` | `string` | Yes | 작업 설명 |
| `tools` | `list` | No | 사용 가능한 도구 정의 목록. 기본 `[]` |
| `model` | `string` | No | AI 모델. 기본 `"default"` |
| `system_prompt` | `string` | 아니오 | 시스템 프롬프트 |

**처리**: `engine.plan()`를 호출합니다. 일반 `execute`와 달리 시스템 프롬프트에 "PLANNING 모드. 도구 불러오기. 단계별 계획을 번호 매기기 목록으로 반환합니다."라는 지시를 추가하여 AI를 호출합니다.

**반환값**:

```json
{
  "status": "ok",
  "data": {
    "execution_id": "agent_xxx",
    "status": "planned",
    "plan": "1. First step...\n2. Second step...\n3. ...",
    "result": { "...execution details..." }
  }
}
```

## 태스크 중 지시 추가 (add_instruction)

**handler**: `defaults.agent.add_instruction`(`blocks/agent/add_instruction.py`)

**HTTP**: `POST /api/agent/{id}/instruct`

**input_data**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 실행 ID(URL 경로에서 자동 주입) |
| `instruction` | `string` | Yes | 추가 지침 |
| `priority` | `string` | 아니오 | `"normal"` 또는 `"urgent"`. 기본 `"normal"` |

**처리**: `InstructionQueue.add_instruction()`에서 지침을 대기열에 추가합니다. 표시는 다음 AI completion 단계 전에 `AgentEngine._inject_pending_instructions()`에 의해 메시지 기록에 주입됩니다. `urgent`의 경우 `[RUNTIME INSTRUCTION — URGENT: Override current approach]` 접두사가 붙습니다. `normal`의 경우 `[RUNTIME INSTRUCTION — Additional guidance from user]` 접두사가 붙습니다.

**반환값**:

```json
{
  "status": "ok",
  "data": {
    "instruction_id": "uuid",
    "execution_id": "agent_xxx",
    "priority": "normal",
    "status": "queued"
  }
}
```

## 모든 API 엔드 포인트 목록

| 메소드 | 경로 | handler 파일 |
|---|---|---|
| `POST` | `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST` | `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST` | `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST` | `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET` | `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST` | `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| — | — (`call_handler`를 통해서만) |`blocks/agent/plan.py` |
