from blocks._common import error, ok
from domain.agent.agent_runtime import AgentRuntime


def run(input_data, context):
    del context
    agent_id = str((input_data or {}).get("agent_id") or (input_data or {}).get("id") or "").strip()
    if not agent_id:
        return error("agent_id is required", "INVALID_INPUT")
    return ok({"state": AgentRuntime().resume(agent_id)})
