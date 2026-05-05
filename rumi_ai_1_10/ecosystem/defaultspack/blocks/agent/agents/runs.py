from blocks._common import ok
from domain.agent.agent_runtime import AgentRuntime


def run(input_data, context):
    del context
    input_data = input_data or {}
    return ok(
        AgentRuntime().runs(
            str(input_data.get("agent_id") or input_data.get("id") or ""),
            limit=int(input_data.get("limit", 50) or 50),
            offset=int(input_data.get("offset", 0) or 0),
        )
    )
