import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import gen_id, timestamp
from domain.agent.execution import AgentExecution
from domain.tool.schema_adapter import (
    adapt_tool_definitions,
    build_tool_execution_context,
    connected_tool_names,
    filter_tool_definitions_for_runtime_profile,
    max_tool_calls,
    runtime_profile_enforced_tool_names,
    tool_name_from_definition,
)

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

    def _ai_complete(self, messages, model, context, tools=None):
        from blocks.ai.complete import run as ai_complete_run
        result = ai_complete_run({"messages": messages, "model": model, "tools": tools or []}, context)
        return result

    def _execute_tool(self, tool_name, tool_args, context):
        from blocks.tool.invoke import run as tool_invoke_run
        result = tool_invoke_run({"tool_name": tool_name, "arguments": tool_args}, context)
        return result

    def _tool_name_from_definition(self, tool):
        return tool_name_from_definition(tool)

    def _connected_tool_names(self, execution):
        runtime_profile = getattr(execution, "context", {}).get("runtime_profile")
        agent_id = getattr(execution, "context", {}).get("agent_id")
        return connected_tool_names(execution.tools, runtime_profile, agent_id)

    def _enforced_tool_names(self, execution):
        context = getattr(execution, "context", {}) or {}
        return runtime_profile_enforced_tool_names(
            context.get("runtime_profile"),
            context.get("agent_id"),
            execution.tools,
        )

    def _tool_call_count(self, execution):
        return sum(1 for step in execution.steps if step.step_type == "tool_result")

    def _normalize_tool_args(self, tool_args):
        if isinstance(tool_args, str):
            try:
                parsed = json.loads(tool_args)
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except (TypeError, ValueError):
                return {"value": tool_args}
        if isinstance(tool_args, dict):
            return tool_args
        return {}

    def _reject_unconnected_tool_call(self, execution, parsed):
        connected_tools = self._connected_tool_names(execution)
        enforced_tools = self._enforced_tool_names(execution)
        tool_name = parsed.get("tool_name", "")
        allowed_tools = enforced_tools if enforced_tools is not None else connected_tools
        if tool_name in allowed_tools:
            return False
        execution.status = "error"
        execution.error = "tool call is not connected to this agent: " + tool_name
        execution.add_step("error", {
            "error": execution.error,
            "tool_name": tool_name,
            "connected_tools": sorted(connected_tools),
            "enforced_tools": sorted(enforced_tools) if enforced_tools is not None else None,
        })
        return True

    def _reject_policy_violation(self, execution, parsed):
        limit = max_tool_calls(getattr(execution, "context", {}) or {})
        if limit is None or self._tool_call_count(execution) < limit:
            return False
        tool_name = parsed.get("tool_name", "")
        execution.status = "error"
        execution.error = "max tool calls exceeded"
        execution.add_step("error", {
            "error": execution.error,
            "tool_name": tool_name,
            "max_tool_calls": limit,
        })
        return True

    def _set_pending_tool_call(self, execution, parsed):
        execution.status = "waiting_approval"
        execution.pending_tool_call = {
            "tool_name": parsed["tool_name"],
            "tool_args": self._normalize_tool_args(parsed["tool_args"]),
            "raw": parsed.get("raw", {}),
        }
        execution.add_step("tool_call", {
            "tool_name": parsed["tool_name"],
            "tool_args": execution.pending_tool_call["tool_args"],
        })
        step = execution.steps[-1]
        step.status = "pending"

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
        if isinstance(data, dict) and isinstance(data.get("content"), list):
            for part in data["content"]:
                if not isinstance(part, dict) or part.get("type") not in {"tool_use", "tool_call"}:
                    continue
                return {
                    "type": "tool_call",
                    "tool_name": part.get("name", "unknown"),
                    "tool_args": part.get("input", part.get("args", {})),
                    "raw": part,
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
        execution_context = dict(context or {}) if isinstance(context, dict) else {}
        normalized_tools = adapt_tool_definitions(tools if tools else [])
        provider_tools = filter_tool_definitions_for_runtime_profile(
            normalized_tools,
            execution_context.get("runtime_profile"),
            execution_context.get("agent_id"),
        )
        execution = AgentExecution(
            execution_id=execution_id,
            task=task,
            tools=provider_tools,
            model=model if model else "default",
            system_prompt=system_prompt,
        )
        execution.context = execution_context
        self._executions[execution_id] = execution
        execution.status = "running"
        execution.messages = self._build_initial_messages(execution)
        execution.add_step("think", {"action": "start", "task": task})
        self._inject_pending_instructions(execution)
        ai_result = self._ai_complete(execution.messages, execution.model, execution.context, execution.tools)
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
            if self._reject_unconnected_tool_call(execution, parsed) or self._reject_policy_violation(execution, parsed):
                return {
                    "execution_id": execution_id,
                    "status": "error",
                    "result": execution.to_dict(),
                }
            self._set_pending_tool_call(execution, parsed)
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
        context_for_tool = dict(getattr(execution, "context", {}) or {})
        context_for_tool = build_tool_execution_context(
            context_for_tool,
            pending["tool_name"],
            self._connected_tool_names(execution),
        )
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
        ai_result = self._ai_complete(execution.messages, execution.model, context_for_tool, execution.tools)
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
            if self._reject_unconnected_tool_call(execution, parsed) or self._reject_policy_violation(execution, parsed):
                return {
                    "execution_id": execution_id,
                    "status": "error",
                    "result": execution.to_dict(),
                }
            self._set_pending_tool_call(execution, parsed)
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
        context_for_ai = dict(getattr(execution, "context", {}) or {})
        ai_result = self._ai_complete(execution.messages, execution.model, context_for_ai, execution.tools)
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
            if self._reject_unconnected_tool_call(execution, parsed) or self._reject_policy_violation(execution, parsed):
                return {
                    "execution_id": execution_id,
                    "status": "error",
                    "result": execution.to_dict(),
                }
            self._set_pending_tool_call(execution, parsed)
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
        execution_context = dict(context or {}) if isinstance(context, dict) else {}
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
        execution.context = execution_context
        self._executions[execution_id] = execution
        execution.status = "running"
        messages = []
        messages.append({"role": "system", "content": plan_system})
        messages.append({"role": "user", "content": task})
        execution.messages = messages
        execution.add_step("plan", {"action": "planning", "task": task})
        ai_result = self._ai_complete(messages, execution.model, execution.context, [])
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
