<!-- docs-i18n-links:start -->
[EN](../../agent.md) | [JP](../ja/agent.md) | [KR](./agent.md) | [CN](../zh-cn/agent.md)
<!-- docs-i18n-links:end -->

# 에이전트 API

기본 팩의 에이전트 기능에 대한 전체 API 참조입니다. 핸들러는 `blocks/agent/`에서 구현되고, 도메인 로직은 `domain/agent/engine.py`(AgentEngine) 및 `domain/agent/execution.py`(AgentExecution)에서 구현됩니다.

## 에이전트 개념

에이전트는 "작업을 받고, AI가 몇 가지 생각을 하고, 필요한 경우 도구를 호출하고, 결과를 반환하는" 실행 루프입니다. 기본 팩 에이전트는 다음 흐름을 사용하여 구현됩니다.

1. 사용자는 작업 및 사용 가능한 도구를 사용하여 `execute`을 호출합니다.
2. `AgentEngine`은 초기 메시지(system_prompt + task)를 구성하여 AI에 보냅니다.
3. AI가 “텍스트 응답”을 반환하는 경우 → 작업 완료(상태: `completed`).
4. AI가 “툴 콜”을 반환하는 경우 → 사용자 승인 대기 중(상태:`waiting_approval`).
5. 사용자 `approve` → 도구 실행 → 결과를 AI로 반환 → 3으로 돌아갑니다.
6. 사용자 `reject` → 거부 사유를 AI에 반환 → AI가 대안 제안 → 3단계로 돌아갑니다.
7. 공구 호출 깊이가 `MAX_FLOW_CALL_DEPTH` (10)에 도달한 경우 → 오류입니다.

`blocks/agent/_state.py`은 메모리 내에서 실행되는 `AgentEngine` 인스턴스를 관리합니다. `execution_id`를 키로 `set_engine()` / `get_engine()` / `remove_engine()`에서 관리됩니다.

## 태스크 실행(실행)

**처리기**: `defaults.agent.execute`(`blocks/agent/execute.py`)**HTTP**: `POST /api/agent/execute`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `tools` | `list` | No | List of available tool definitions. Default `[]` |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |

**처리 중**: `AgentEngine().execute(task, tools, model, system_prompt, context)`으로 전화하세요. 초기 메시지를 작성하여 AI에 보내고 응답에 따라 `completed` / `waiting_approval` / `error` 상태를 반환합니다.**반환 값**:

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

## 승인

**처리기**: `defaults.agent.approve`(`blocks/agent/approve.py`)**HTTP**: `POST /api/agent/{id}/approve`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**처리 중**: `engine.approve(execution_id)`으로 전화하세요. 보류 중인 도구를 실행하고 결과를 AI에 반환하고 다음 응답을 받습니다. AI가 더 많은 도구를 호출하면 다시 `waiting_approval`가 됩니다.**반환 값**: `ok(result)` — 업데이트된 실행 상태.

## 거부

**처리기**: `defaults.agent.reject`(`blocks/agent/reject.py`)**HTTP**: `POST /api/agent/{id}/reject`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |
| `reason` | `string` | No | Reason for refusal. Default `"Rejected by user"` |

**처리 중**: `engine.reject(execution_id, reason)`으로 전화하세요. "사용자가 도구 호출을 거부했습니다. 이유: {reason}. 대안을 제안하십시오."**반환 값**: `ok(result)` — 업데이트된 실행 상태.

## 취소

**처리기**: `defaults.agent.cancel`(`blocks/agent/cancel.py`)**HTTP**: `POST /api/agent/{id}/cancel`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**처리 중**: `engine.cancel(execution_id)`을 호출하고 `_state.remove_engine(execution_id)`의 메모리에서 엔진을 제거합니다. `InstructionQueue`의 해당 실행 지침도 지워집니다.**반환 값**: `ok({"execution_id": "...", "status": "cancelled"})`

## 상태 확인

**처리기**: `defaults.agent.status`(`blocks/agent/status.py`)**HTTP**: `GET /api/agent/{id}/status`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**반환 값**:

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

## 계획만(계획)

**처리자**: `defaults.agent.plan`(`blocks/agent/plan.py`)

HTTP 경로가 현재 정의되지 않았습니다. `call_handler("defaults.agent.plan", ...)`을 통해서만 호출할 수 있습니다.

**입력_데이터**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `tools` | `list` | No | List of available tool definitions. Default `[]` |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |

**처리 중**: `engine.plan()`으로 전화하세요. 일반 `execute`과 달리 시스템 프롬프트에 다음 지침을 추가하여 AI를 호출합니다. "PLANNING 모드. 도구를 호출하지 마십시오. 번호가 매겨진 목록으로 단계별 계획을 반환합니다."**반환 값**:

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

## 작업 중 지침 추가(add_instruction)

**처리기**: `defaults.agent.add_instruction`(`blocks/agent/add_instruction.py`)**HTTP**: `POST /api/agent/{id}/instruct`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |
| `instruction` | `string` | Yes | Additional instructions |
| `priority` | `string` | No | `"normal"` or `"urgent"`. Default `"normal"` |

**처리 중**: `InstructionQueue.add_instruction()`을 사용하여 명령을 대기열에 추가합니다. 지침은 다음 AI 완료 단계 전에 `AgentEngine._inject_pending_instructions()`에 의해 메시지 기록에 삽입됩니다. `urgent`에는 `[RUNTIME INSTRUCTION — URGENT: Override current approach]` 접두사가 있습니다. `normal`에는 `[RUNTIME INSTRUCTION — Additional guidance from user]` 접두사가 있습니다.**반환 값**:

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

## 모든 API 엔드포인트 목록

| method | path | handler file |
|---|---|---|
| `POST` | `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST` | `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST` | `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST` | `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET` | `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST` | `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| — | — (only via `call_handler`) | `blocks/agent/plan.py` |
