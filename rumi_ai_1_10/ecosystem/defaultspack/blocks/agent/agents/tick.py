import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import error, ok
from domain.agent.agent_runtime import AgentRuntime


def run(input_data, context):
    input_data = input_data or {}
    agent_id = str(input_data.get("agent_id") or input_data.get("id") or "").strip()
    if not agent_id:
        return error("agent_id is required", "INVALID_INPUT")
    result = AgentRuntime().tick(
        agent_id,
        message=input_data.get("message", ""),
        conversation_id=input_data.get("conversation_id", ""),
        trigger=input_data.get("trigger", "manual"),
        schedule_id=input_data.get("schedule_id", ""),
        schedule_execution_id=input_data.get("schedule_execution_id", ""),
        model=input_data.get("model", ""),
        tools=input_data.get("tools") if isinstance(input_data.get("tools"), list) else None,
        tool_policy=input_data.get("tool_policy") if isinstance(input_data.get("tool_policy"), dict) else {},
        metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {},
        context=context if isinstance(context, dict) else {},
    )
    if result.get("status") in {"error", "failed"}:
        return error(str(result.get("error") or result.get("blocked_reason") or "agent tick failed"), "AGENT_TICK_FAILED")
    return ok(result)
