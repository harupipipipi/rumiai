<!-- docs-i18n-links:start -->
[EN](../../agent.md) | [JP](../ja/agent.md) | [KR](../ko/agent.md) | [CN](./agent.md)
<!-- docs-i18n-links:end -->

# 代理API

默认包中代理功能的完整 API 参考。处理程序在`blocks/agent/`中实现，域逻辑在`domain/agent/engine.py`（AgentEngine）和`domain/agent/execution.py`（AgentExecution）中实现。

## 代理概念

代理是一个执行循环，“接收任务，人工智能进行一些思考，必要时调用工具，然后返回结果”。默认包代理是使用以下流程实现的。

1. 用户使用任务和可用工具调用`execute`。
2.`AgentEngine`构建初始消息（system_prompt +任务）并将其发送给AI。
3. 如果人工智能返回“文本响应”→任务已完成（状态：`completed`）。
4. 如果AI返回“工具调用”→等待用户批准（状态：`waiting_approval`）。
5. 用户`approve`→运行工具→将结果返回给AI→返回3。
6. 用户`reject` → 将拒绝原因返回给 AI → AI 建议替代方案 → 返回步骤 3。
7. 如果工具调用深度达到`MAX_FLOW_CALL_DEPTH` (10) → 错误。

`blocks/agent/_state.py` 管理在内存中运行的`AgentEngine` 实例。它在`set_engine()`/`get_engine()`/`remove_engine()`中进行管理，以`execution_id`为密钥。

## 任务执行（execute）

**处理程序**：`defaults.agent.execute`（`blocks/agent/execute.py`）

**HTTP**：`POST /api/agent/execute`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |任务描述|
| §鲁米§0§| §鲁米§1§ |没有 |可用工具定义的列表。默认`[]`|
| §鲁米§0§| §鲁米§1§ |没有 |人工智能模型。默认`"default"` |
| §鲁米§0§| §鲁米§1§ |没有 |系统提示|

**处理**：致电`AgentEngine().execute(task, tools, model, system_prompt, context)`。构建初始消息，将其发送给 AI，并根据响应返回 `completed` / `waiting_approval` / `error` 状态。

**返回值**：

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

## 批准

**处理程序**：`defaults.agent.approve`（`blocks/agent/approve.py`）

**HTTP**：`POST /api/agent/{id}/approve`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |运行 ID（从 URL 路径自动注入）|

**处理**：致电`engine.approve(execution_id)`。运行待处理的工具，将结果返回给AI，并获得下一个响应。如果AI调用更多工具，就会再次变成`waiting_approval`。

**返回值**：`ok(result)` — 更新的执行状态。

## 拒绝

**处理程序**：`defaults.agent.reject`（`blocks/agent/reject.py`）

**HTTP**：`POST /api/agent/{id}/reject`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |运行 ID（从 URL 路径自动注入）|
| §鲁米§0§| §鲁米§1§ |没有 |拒绝原因。默认`"Rejected by user"` |

**处理**：致电`engine.reject(execution_id, reason)`。向 AI 发送一条消息，内容为“用户拒绝了工具调用。原因：{reason}。请建议替代方案。”

**返回值**：`ok(result)` — 更新的执行状态。

## 取消

**处理程序**：`defaults.agent.cancel`（`blocks/agent/cancel.py`）

**HTTP**：`POST /api/agent/{id}/cancel`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |运行 ID（从 URL 路径自动注入）|

**处理**：调用`engine.cancel(execution_id)`并从`_state.remove_engine(execution_id)`中的内存中删除引擎。 `InstructionQueue`中的此类执行指令也被清除。

**返回值**：`ok({"execution_id": "...", "status": "cancelled"})`

## 检查状态

**处理程序**：`defaults.agent.status`（`blocks/agent/status.py`）

**HTTP**：`GET /api/agent/{id}/status`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |运行 ID（从 URL 路径自动注入）|

**返回值**：

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

## 仅计划（计划）

**处理程序**：`defaults.agent.plan`（`blocks/agent/plan.py`）

HTTP 路由当前未定义。只能通过`call_handler("defaults.agent.plan", ...)`调用。

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |任务描述|
| §鲁米§0§| §鲁米§1§ |没有 |可用工具定义的列表。默认`[]`|
| §鲁米§0§| §鲁米§1§ |没有 |人工智能模型。默认`"default"` |
| §鲁米§0§| §鲁米§1§ |没有 |系统提示|

**处理**：致电`engine.plan()`。与常规的`execute`不同，我们通过在系统提示中添加以下指令来调用AI：“规划模式。不要调用工具。在编号列表中返回分步计划。”

**返回值**：

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

## 在任务期间添加指令（add_instruction）

**处理程序**：`defaults.agent.add_instruction`（`blocks/agent/add_instruction.py`）

**HTTP**：`POST /api/agent/{id}/instruct`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |运行 ID（从 URL 路径自动注入）|
| §鲁米§0§| §鲁米§1§ |是的 |附加说明 |
| §鲁米§0§| §鲁米§1§ |没有 | `"normal"`或`"urgent"`。默认`"normal"` |

**处理**：将指令添加到带有`InstructionQueue.add_instruction()`的队列中。在下一个 AI 完成步骤之前，指令由`AgentEngine._inject_pending_instructions()`注入消息历史记录中。 `urgent` 具有 `[RUNTIME INSTRUCTION — URGENT: Override current approach]` 前缀。 `normal` 具有 `[RUNTIME INSTRUCTION — Additional guidance from user]` 前缀。

**返回值**：

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

## 所有 API 端点列表

|方法|路径|处理程序文件 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| — | —（仅通过`call_handler`）| §鲁米§1§ |
