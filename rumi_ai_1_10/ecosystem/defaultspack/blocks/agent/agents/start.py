import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import error, ok
from domain.agent.agent_runtime import AgentRuntime


def run(input_data, context):
    del context
    agent_id = str((input_data or {}).get("agent_id") or (input_data or {}).get("id") or "").strip()
    if not agent_id:
        return error("agent_id is required", "INVALID_INPUT")
    try:
        state = AgentRuntime().start(
            agent_id,
            conversation_id=(input_data or {}).get("conversation_id", ""),
            metadata=(input_data or {}).get("metadata") if isinstance((input_data or {}).get("metadata"), dict) else {},
        )
        return ok({"state": state})
    except Exception as exc:
        return error(str(exc), "AGENT_RUNTIME_ERROR")
