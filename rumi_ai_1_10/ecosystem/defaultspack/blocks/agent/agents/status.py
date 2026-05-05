from blocks._common import ok
from domain.agent.agent_runtime import AgentRuntime


def run(input_data, context):
    del context
    agent_id = str((input_data or {}).get("agent_id") or (input_data or {}).get("id") or "").strip()
    return ok(AgentRuntime().status(agent_id))
