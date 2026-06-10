<!-- docs-i18n-links:start -->
[EN](./multi-agent.md) | [JP](./i18n/ja/multi-agent.md) | [KR](./i18n/ko/multi-agent.md) | [CN](./i18n/zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# Multi-Agent API

A complete API reference for the defaults pack's multi-agent functionality. The handler is implemented in `blocks/agent/multi_*.py` and the domain logic is implemented in `domain/agent/multi.py` (MultiAgentOrchestrator).

## Multi-agent concept

Multi-agent is a system in which multiple AI agents work together to accomplish a task. Each agent is defined in `AgentDefinition` (`domain/agent/agent_def.py`) and has a name, role, model, system prompts, and tools.

`MultiAgentOrchestrator` manages the entire session and exchanges messages between agents through `MessageBus` (in-memory). Each agent has a shared message history and a private message queue.

When an agent's response contains the `[DONE]` marker, the agent is in a completed state. The session ends when all agents complete or the maximum number of turns is reached.

Agents can mention other agents in their responses in the form `@agent_name: message`. `directed` Orchestration uses this mention to determine the next speaker.

## Session creation (multi_execute)

**handler**: `defaults.agent.multi_execute`（`blocks/agent/multi_execute.py`）

**HTTP**: `POST /api/agent/multi/execute`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `agents` | `list[dict]` | Yes | List of agent definitions (at least one) |
| `orchestration` | `string` | No | Any of `"round_robin"`, `"directed"`, `"free"`. Default `"round_robin"` |
| `max_turns` | `int` | No | Maximum number of turns. Default `10`. Positive integer greater than or equal to 1 |

## Agent definition

`agents` Each element of the array is a dict with the following fields.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Agent name (unique). Used for mentions (`@name:`) |
| `role` | `string` | Yes | Role description |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |
| `tools` | `list` | No | Available tool definition list |
| `agent_id` | `string` | No | Unique identifier. Automatically generated if not specified (`agentdef_` + UUID) |

**input_data example**:

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

## Orchestration method

**`round_robin`** (default): Agents speak in turn. `session.current_turn % len(agents)` determines the next speaker. Completed (`done: true`) agents are skipped.

**`directed`**: Determines the next speaker from the `@agent_name:` mention in the previous message. If there are no mentions, it will fall back to round robin. Parsed with `_MENTION_RE = re.compile(r"@(\w+)\s*:")`.

**`free`**: All incomplete agents speak in parallel. Use `threading.Thread` to execute multiple agent turns simultaneously. Each thread has a timeout of 120 seconds.

## Return value

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

## Check status

**handler**: `defaults.agent.multi_status`（`blocks/agent/multi_status.py`）

**HTTP**: `GET /api/agent/multi/{id}/status`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |

**Processing**: Get session at `_state.get_multi_session(session_id)` and return `session.to_dict()` at `orchestrator.get_status(session)`.

**Return value**: `ok(session_dict)` — Complete state of the session.

**Error case**: If `session_id` is unspecified or the session does not exist, return `error(...)`.

## Inputting messages from outside

**handler**: `defaults.agent.multi_message`（`blocks/agent/multi_message.py`）

**HTTP**: `POST /api/agent/multi/{id}/message`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |
| `message` | `string` | Yes | Message content to be input |
| `target_agent` | `string` | No | Name when addressing to a specific agent |

**Processing**: If `target_agent` is specified, send a direct message with `post_direct("user", target, message, turn)` and also add it to the agent's `agent_contexts[name]["messages"]` as `[User message]: ...`. If not specified, it will be posted as a shared message using `post_shared("user", message, turn)` and added to the messages of all agents.

**Return value**: `ok({"session_id": "...", "message": "Message injected successfully"})`

**Error case**: Returns `error(...)` if `session_id` is unspecified, `message` is unspecified, or the session does not exist.

## List of all HTTP endpoints

| method | path | handler file | injected path parameter |
|---|---|---|---|
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` | — |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` | `{id}` → `session_id` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` | `{id}` → `session_id` |
