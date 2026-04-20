import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.agent.multi import MultiAgentOrchestrator
from blocks.agent._state import get_multi_session


def run(input_data, context):
    """defaults.agent.multi_status — マルチエージェントセッションの状態を返す。

    input_data:
        session_id : str (必須) セッションID
    """
    if not isinstance(input_data, dict):
        return error("input_data must be a dict")

    session_id = input_data.get("session_id")
    if not session_id:
        return error("session_id is required")

    session = get_multi_session(session_id)
    if session is None:
        return error("session not found: " + str(session_id))

    orchestrator = MultiAgentOrchestrator()
    status_data = orchestrator.get_status(session)

    return ok(status_data)
