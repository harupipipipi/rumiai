import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import gen_id, timestamp
from domain.agent.execution import AgentExecution

MAX_FLOW_CALL_DEPTH = 10


class AgentEngine:
    def __init__(self):
        self._executions = {}

    def _get_instruction_queue(self):
        try:
            from blocks.agent._state import get_instruction_queue
            return get_instruction_queue()
        except Exception:
            return None

    def _inject_pending_instructions(self, execution):
        queue = self._get_instruction_queue()
        if queue is None:
            return False
        if not queue.has_pending(execution.execution_id):
            return False
        pending = queue.get_pending(execution.execution_id)
        if not pending:
            return False
        parts = []
        has_urgent = False
        for instr in pending:
            prefix = "[URGENT] " if instr["priority"] == "urgent" else ""
            parts.append(prefix + instr["instruction"])
            if instr["priority"] == "urgent":
                has_urgent = True
        if len(parts) == 1:
            combined = parts[0]
        else:
            combined = "\n".join(
                "- " + p for p in parts
            )
        header = (
            "[RUNTIME INSTRUCTION — URGENT: Override current approach] "
            if has_urgent
            else "[RUNTIME INSTRUCTION — Additional guidance from user] "
        )
        message_content = header + combined
        execution.messages.append({"role": "user", "content": message_content})
        execution.add_step("instruction_injected", {
            "count": len(pending),
            "has_urgent": has_urgent,
            "instructions": [
                {"id": i["id"], "priority": i["priority"], "instruction": i["instruction"]}
                for i in pending
            ],
        })
        return True

    def _ai_complete(self, messages, model, context):
        from blocks.ai.complete import run as ai_complete_run
        result = ai_complete_run({"messages": messages, "model": model}, context)
        return result

    def _execute_tool(self, tool_name, tool_args, context):
        from blocks.tool.invoke import run as tool_invoke_run
        result = tool_invoke_run({"tool_name": tool_name, "args": tool_args}, context)
        return result

    def _parse_ai_response(self, ai_result):
        if ai_result.get("status") != "ok":
            return {
                "type": "error",
                "content": ai_result.get("error", "AI call failed"),
            }
        data = ai_result.get("data", {})
        if isinstance(data, dict) and data.get("tool_calls"):
            tool_calls = data["tool_calls"]
            first_call = tool_calls[0] if isinstance(tool_calls, list) and len(tool_calls) > 0 else tool_calls
            return {
                "type": "tool_call",
                "tool_name": first_call.get("name", first_call.get("function", {}).get("name", "unknown")),
                "tool_args": first_call.get("args", first_call.get("function", {}).get("arguments", {})),
                "raw": first_call,
            }
        content = ""
        if isinstance(data, dict):
            content = data.get("content", data.get("text", str(data)))
        elif isinstance(data, str):
            content = data
        else:
            content = str(data)
        return {"type": "text", "content": content}

    def _build_initial_messages(self, execution):
        messages = []
        if execution.system_prompt:
            messages.append({"role": "system", "content": execution.system_prompt})
        messages.append({"role": "user", "content": execution.task})
        return messages

    def execute(self, task, tools, model, system_prompt, context):
        execution_id = gen_id("agent_")
        execution = AgentExecution(
            execution_id=execution_id,
            task=task,
            tools=tools if tools else [],
            model=model if model else "default",
            system_prompt=system_prompt,
        )
        self._executions[execution_id] = execution
        execution.status = "running"
        execution.messages = self._build_initial_messages(execution)
        execution.add_step("think", {"action": "start", "task": task})
        self._inject_pending_instructions(execution)
        ai_result = self._ai_complete(execution.messages, execution.model, context)
        parsed = self._parse_ai_response(ai_result)
        if parsed["type"] == "error":
            execution.status = "error"
            execution.error = parsed["content"]
            execution.add_step("error", {"error": parsed["content"]})
            return {
                "execution_id": execution_id,
                "status": "error",
                "result": execution.to_dict(),
            }
        if parsed["type"] == "tool_call":
            execution.status = "waiting_approval"
            execution.pending_tool_call = {
                "tool_name": parsed["tool_name"],
                "tool_args": parsed["tool_args"],
                "raw": parsed.get("raw", {}),
            }
            execution.add_step("tool_call", {
                "tool_name": parsed["tool_name"],
                "tool_args": parsed["tool_args"],
            })
            step = execution.steps[-1]
            step.status = "pending"
            return {
                "execution_id": execution_id,
                "status": "waiting_approval",
                "result": execution.to_dict(),
            }
        execution.status = "completed"
        execution.result = parsed["content"]
        execution.messages.append({"role": "assistant", "content": parsed["content"]})
        execution.add_step("response", {"content": parsed["content"]})
        return {
            "execution_id": execution_id,
            "status": "completed",
            "result": execution.to_dict(),
        }

    def approve(self, execution_id):
        execution = self._executions.get(execution_id)
        if not execution:
            return {"execution_id": execution_id, "status": "error", "result": {"error": "execution not found"}}
        if execution.status != "waiting_approval":
            return {
                "execution_id": execution_id,
                "status": "error",
                "result": {"error": "execution is not waiting for approval, current status: " + execution.status},
            }
        pending = execution.pending_tool_call
        if not pending:
            return {"execution_id": execution_id, "status": "error", "result": {"error": "no pending tool call"}}
        execution.status = "running"
        execution.pending_tool_call = None
        context_for_tool = {}
        tool_result = self._execute_tool(pending["tool_name"], pending["tool_args"], context_for_tool)
        tool_content = ""
        if isinstance(tool_result, dict):
            tool_content = tool_result.get("data", tool_result.get("error", str(tool_result)))
        else:
            tool_content = str(tool_result)
        execution.add_step("tool_result", {
            "tool_name": pending["tool_name"],
            "result": tool_content,
        })
        execution.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [pending.get("raw", {"name": pending["tool_name"], "args": pending["tool_args"]})],
        })
        execution.messages.append({
            "role": "tool",
            "content": str(tool_content) if not isinstance(tool_content, str) else tool_content,
            "name": pending["tool_name"],
        })
        depth = sum(1 for s in execution.steps if s.step_type == "tool_call")
        if depth >= MAX_FLOW_CALL_DEPTH:
            execution.status = "error"
            execution.error = "max flow call depth exceeded"
            execution.add_step("error", {"error": "max flow call depth exceeded"})
            return {
                "execution_id": execution_id,
                "status": "error",
                "result": execution.to_dict(),
            }
        self._inject_pending_instructions(execution)
        ai_result = self._ai_complete(execution.messages, execution.model, context_for_tool)
        parsed = self._parse_ai_response(ai_result)
        if parsed["type"] == "error":
            execution.status = "error"
            execution.error = parsed["content"]
            execution.add_step("error", {"error": parsed["content"]})
            return {
                "execution_id": execution_id,
                "status": "error",
                "result": execution.to_dict(),
            }
        if parsed["type"] == "tool_call":
            execution.status = "waiting_approval"
            execution.pending_tool_call = {
                "tool_name": parsed["tool_name"],
                "tool_args": parsed["tool_args"],
                "raw": parsed.get("raw", {}),
            }
            execution.add_step("tool_call", {
                "tool_name": parsed["tool_name"],
                "tool_args": parsed["tool_args"],
            })
            step = execution.steps[-1]
            step.status = "pending"
            return {
                "execution_id": execution_id,
                "status": "waiting_approval",
                "result": execution.to_dict(),
            }
        execution.status = "completed"
        execution.result = parsed["content"]
        execution.messages.append({"role": "assistant", "content": parsed["content"]})
        execution.add_step("response", {"content": parsed["content"]})
        return {
            "execution_id": execution_id,
            "status": "completed",
            "result": execution.to_dict(),
        }

    def reject(self, execution_id, reason):
        execution = self._executions.get(execution_id)
        if not execution:
            return {"execution_id": execution_id, "status": "error", "result": {"error": "execution not found"}}
        if execution.status != "waiting_approval":
            return {
                "execution_id": execution_id,
                "status": "error",
                "result": {"error": "execution is not waiting for approval, current status: " + execution.status},
            }
        if not reason:
            reason = "Rejected by user"
        execution.status = "running"
        pending = execution.pending_tool_call
        execution.pending_tool_call = None
        rejection_msg = (
            "The user rejected the tool call to '"
            + (pending["tool_name"] if pending else "unknown")
            + "'. Reason: "
            + reason
            + ". Please suggest an alternative approach."
        )
        execution.messages.append({"role": "user", "content": rejection_msg})
        execution.add_step("think", {"action": "rejection", "reason": reason})
        self._inject_pending_instructions(execution)
        ai_result = self._ai_complete(execution.messages, execution.model, {})
        parsed = self._parse_ai_response(ai_result)
        if parsed["type"] == "error":
            execution.status = "error"
            execution.error = parsed["content"]
            execution.add_step("error", {"error": parsed["content"]})
            return {
                "execution_id": execution_id,
                "status": "error",
                "result": execution.to_dict(),
            }
        if parsed["type"] == "tool_call":
            execution.status = "waiting_approval"
            execution.pending_tool_call = {
                "tool_name": parsed["tool_name"],
                "tool_args": parsed["tool_args"],
                "raw": parsed.get("raw", {}),
            }
            execution.add_step("tool_call", {
                "tool_name": parsed["tool_name"],
                "tool_args": parsed["tool_args"],
            })
            step = execution.steps[-1]
            step.status = "pending"
            return {
                "execution_id": execution_id,
                "status": "waiting_approval",
                "result": execution.to_dict(),
            }
        execution.status = "completed"
        execution.result = parsed["content"]
        execution.messages.append({"role": "assistant", "content": parsed["content"]})
        execution.add_step("response", {"content": parsed["content"]})
        return {
            "execution_id": execution_id,
            "status": "completed",
            "result": execution.to_dict(),
        }

    def cancel(self, execution_id):
        execution = self._executions.get(execution_id)
        if not execution:
            return {"execution_id": execution_id, "status": "error", "result": {"error": "execution not found"}}
        execution.status = "cancelled"
        execution.pending_tool_call = None
        execution.updated_at = timestamp()
        execution.add_step("think", {"action": "cancelled"})
        return {"execution_id": execution_id, "status": "cancelled"}

    def status(self, execution_id):
        execution = self._executions.get(execution_id)
        if not execution:
            return {"execution_id": execution_id, "status": "error", "result": {"error": "execution not found"}}
        return {
            "execution_id": execution_id,
            "status": execution.status,
            "steps": [s.to_dict() for s in execution.steps],
            "current_step": execution.current_step,
        }

    def plan(self, task, tools, model, system_prompt, context):
        execution_id = gen_id("agent_")
        plan_system = system_prompt if system_prompt else ""
        plan_system += (
            "\n\nYou are in PLANNING mode. Do NOT execute any actions. "
            "Create a step-by-step plan for the following task. "
            "Return the plan as a numbered list. Do not call any tools."
        )
        execution = AgentExecution(
            execution_id=execution_id,
            task=task,
            tools=[],
            model=model if model else "default",
            system_prompt=plan_system,
        )
        self._executions[execution_id] = execution
        execution.status = "running"
        messages = []
        messages.append({"role": "system", "content": plan_system})
        messages.append({"role": "user", "content": task})
        execution.messages = messages
        execution.add_step("plan", {"action": "planning", "task": task})
        ai_result = self._ai_complete(messages, execution.model, context)
        parsed = self._parse_ai_response(ai_result)
        if parsed["type"] == "error":
            execution.status = "error"
            execution.error = parsed["content"]
            execution.add_step("error", {"error": parsed["content"]})
            return {
                "execution_id": execution_id,
                "status": "error",
                "result": execution.to_dict(),
            }
        plan_content = parsed.get("content", "")
        if parsed["type"] == "tool_call":
            plan_content = "Agent attempted tool call during planning: " + str(parsed)
        execution.status = "planned"
        execution.result = plan_content
        execution.add_step("plan", {"plan": plan_content})
        return {
            "execution_id": execution_id,
            "status": "planned",
            "plan": plan_content,
            "result": execution.to_dict(),
        }
