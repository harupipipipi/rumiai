<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](../ja/multi-agent.md) | [KR](../ko/multi-agent.md) | [CN](./multi-agent.md)
<!-- docs-i18n-links:end -->

# 多代理API

默认包的多代理功能的完整 API 参考。处理程序在 `blocks/agent/multi_*.py` 中实现，域逻辑在 `domain/agent/multi.py` (MultiAgentOrchestrator) 中实现。

## 多代理概念

多智能体是多个人工智能智能体协同工作来完成任务的系统。每个代理在 `AgentDefinition` (`domain/agent/agent_def.py`) 中定义，并具有名称、角色、模型、系统提示和工具。

`MultiAgentOrchestrator` 管理整个会话并通过`MessageBus`（内存中）在代理之间交换消息。每个代理都有一个共享的消息历史记录和一个私有的消息队列。

当代理的响应包含 `[DONE]` 标记时，代理处于已完成状态。当所有代理完成或达到最大轮数时，会话结束。

代理可以在其回复中以 `@agent_name: message` 的形式提及其他代理。 `directed` 编排使用此提及来确定下一个发言者。

## 会话创建（multi_execute）

**处理程序**：`defaults.agent.multi_execute`（`blocks/agent/multi_execute.py`）**HTTP**：`POST /api/agent/multi/execute`**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `agents` | `list[dict]` | Yes | List of agent definitions (at least one) |
| `orchestration` | `string` | No | Any of `"round_robin"`, `"directed"`, `"free"`. Default `"round_robin"` |
| `max_turns` | `int` | No | Maximum number of turns. Default `10`. Positive integer greater than or equal to 1 |

## 代理定义

`agents` 数组的每个元素都是一个具有以下字段的字典。

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Agent name (unique). Used for mentions (`@name:`) |
| `role` | `string` | Yes | Role description |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |
| `tools` | `list` | No | Available tool definition list |
| `agent_id` | `string` | No | Unique identifier. Automatically generated if not specified (`agentdef_` + UUID) |

**输入数据示例**：

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

## 编排方法

**`round_robin`**（默认）：座席轮流发言。 `session.current_turn % len(agents)` 决定下一位发言者。已完成的 (`done: true`) 代理将被跳过。**`directed`**：根据上一条消息中提及的 `@agent_name:` 确定下一个发言者。如果没有提及，则将退回到循环赛。用 `_MENTION_RE = re.compile(r"@(\w+)\s*:")` 解析。

**`free`**：所有不完整的代理并行发言。使用`threading.Thread`同时执行多个代理回合。每个线程的超时时间为 120 秒。

## 返回值

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

## 检查状态

**处理程序**：`defaults.agent.multi_status`（`blocks/agent/multi_status.py`）**HTTP**：`GET /api/agent/multi/{id}/status`**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |

**处理**：在`_state.get_multi_session(session_id)`处获取会话并在`orchestrator.get_status(session)`处返回`session.to_dict()`。**返回值**：`ok(session_dict)` - 会话的完整状态。**错误情况**：如果未指定`session_id`或会话不存在，则返回`error(...)`。

## 从外部输入消息

**处理程序**：`defaults.agent.multi_message`（`blocks/agent/multi_message.py`）**HTTP**：`POST /api/agent/multi/{id}/message`**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |
| `message` | `string` | Yes | Message content to be input |
| `target_agent` | `string` | No | Name when addressing to a specific agent |

**处理**：如果指定了 `target_agent`，请发送包含 `post_direct("user", target, message, turn)` 的直接消息，并将其作为 `[User message]: ...` 添加到代理的 `agent_contexts[name]["messages"]` 中。如果未指定，它将使用`post_shared("user", message, turn)`作为共享消息发布，并添加到所有代理的消息中。**返回值**：`ok({"session_id": "...", "message": "Message injected successfully"})`**错误情况**：如果未指定`session_id`、`message`或会话不存在，则返回`error(...)`。

## 所有 HTTP 端点的列表

| method | path | handler file | injected path parameter |
|---|---|---|---|
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` | — |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` | `{id}` → `session_id` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` | `{id}` → `session_id` |
