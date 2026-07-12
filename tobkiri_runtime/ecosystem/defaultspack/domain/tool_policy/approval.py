from __future__ import annotations

from blocks._common import gen_id
from domain.agent_runtime.run_store import AgentRunStore


def request_tool_approval(run_id: str, tool_name: str, reason: str) -> str:
    approval_id = gen_id("approval_")
    tool_call_id = gen_id("call_")
    AgentRunStore().record_tool_call(run_id, tool_call_id, tool_name, {}, status="pending", approval_id=approval_id)
    AgentRunStore().record_approval(approval_id, run_id, tool_call_id, status="pending", reason=reason)
    return approval_id
