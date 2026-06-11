<!-- docs-i18n-links:start -->
[EN](./agent.md) | [JP](./i18n/ja/agent.md) | [KR](./i18n/ko/agent.md) | [CN](./i18n/zh-cn/agent.md)
<!-- docs-i18n-links:end -->

# Agent API

A complete API reference for agent functionality in the defaults pack. The handler is implemented in `blocks/agent/`, and the domain logic is implemented in `domain/agent/engine.py` (AgentEngine) and `domain/agent/execution.py` (AgentExecution).

## Agent concept

The agent is an execution loop that "receives a task, the AI does some thinking, calls tools if necessary, and returns a result." The defaults pack agent is implemented using the following flow.

1. The user calls `execute` with the task and available tools.
2. `AgentEngine` constructs the initial message (system_prompt + task) and sends it to the AI.
3. If the AI returns a “text response” → task completed (status: `completed`).
4. If AI returns “tool call” → Waiting for user approval (status: `waiting_approval`).
5. User `approve` → Run tool → Return results to AI → Return to 3.
6. User `reject` → Returns rejection reason to AI → AI suggests alternative → Return to step 3.
7. If the tool call depth reaches `MAX_FLOW_CALL_DEPTH` (10) → Error.

`blocks/agent/_state.py` manages `AgentEngine` instances running in-memory. It is managed in `set_engine()` / `get_engine()` / `remove_engine()` with `execution_id` as the key.

## Task execution (execute)

**handler**: `defaults.agent.execute`（`blocks/agent/execute.py`）**HTTP**: `POST /api/agent/execute`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `tools` | `list` | No | List of available tool definitions. Default `[]` |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |

**Processing**: Call `AgentEngine().execute(task, tools, model, system_prompt, context)`. Build an initial message, send it to the AI, and return a status of either `completed` / `waiting_approval` / `error` depending on the response.**Return value**:

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

## Approve

**handler**: `defaults.agent.approve`（`blocks/agent/approve.py`）**HTTP**: `POST /api/agent/{id}/approve`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**Processing**: Call `engine.approve(execution_id)`. Run the pending tool, return the results to the AI, and get the next response. If the AI ​​calls more tools, it will become `waiting_approval` again.**Return value**: `ok(result)` — Updated execution state.

## reject

**handler**: `defaults.agent.reject`（`blocks/agent/reject.py`）**HTTP**: `POST /api/agent/{id}/reject`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |
| `reason` | `string` | No | Reason for refusal. Default `"Rejected by user"` |

**Processing**: Call `engine.reject(execution_id, reason)`. Send a message to the AI ​​that says "User declined the tool call. Reason: {reason}. Please suggest an alternative."**Return value**: `ok(result)` — Updated execution state.

## Cancel

**handler**: `defaults.agent.cancel`（`blocks/agent/cancel.py`）**HTTP**: `POST /api/agent/{id}/cancel`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**Processing**: Call `engine.cancel(execution_id)` and remove the engine from memory in `_state.remove_engine(execution_id)`. The instructions for such execution in `InstructionQueue` are also cleared.**Return value**: `ok({"execution_id": "...", "status": "cancelled"})`

## Check status

**handler**: `defaults.agent.status`（`blocks/agent/status.py`）**HTTP**: `GET /api/agent/{id}/status`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**Return value**:

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

## Plan only (plan)

**handler**: `defaults.agent.plan`（`blocks/agent/plan.py`）

HTTP route is currently undefined. Can only be called via `call_handler("defaults.agent.plan", ...)`.

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `tools` | `list` | No | List of available tool definitions. Default `[]` |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |

**Processing**: Call `engine.plan()`. Unlike the regular `execute`, we call the AI ​​by adding the following instruction to the system prompt: "PLANNING mode. Do not call tools. Return step-by-step plan in numbered list."**Return value**:

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

## Add instructions during task (add_instruction)

**handler**: `defaults.agent.add_instruction`（`blocks/agent/add_instruction.py`）**HTTP**: `POST /api/agent/{id}/instruct`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |
| `instruction` | `string` | Yes | Additional instructions |
| `priority` | `string` | No | `"normal"` or `"urgent"`. Default `"normal"` |

**Processing**: Add the instruction to the queue with `InstructionQueue.add_instruction()`. Instructions are injected into the message history by `AgentEngine._inject_pending_instructions()` before the next AI completion step. `urgent` has the `[RUNTIME INSTRUCTION — URGENT: Override current approach]` prefix. `normal` has the `[RUNTIME INSTRUCTION — Additional guidance from user]` prefix.**Return value**:

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

## List of all API endpoints

| method | path | handler file |
|---|---|---|
| `POST` | `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST` | `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST` | `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST` | `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET` | `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST` | `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| — | — (only via `call_handler`) | `blocks/agent/plan.py` |
