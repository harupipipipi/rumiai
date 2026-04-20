import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.agent.multi import MultiAgentOrchestrator
from blocks.agent._state import get_multi_session


def run(input_data, context):
    """defaults.agent.multi_message — 実行中のマルチエージェントセッションに外部からメッセージを投入する。

    input_data:
        session_id   : str (必須) セッションID
        message      : str (必須) 投入するメッセージ
        target_agent : str (任意) 特定エージェント宛にする場合の名前
    """
    if not isinstance(input_data, dict):
        return error("input_data must be a dict")

    session_id = input_data.get("session_id")
    if not session_id:
        return error("session_id is required")

    message = input_data.get("message")
    if not message:
        return error("message is required")

    session = get_multi_session(session_id)
    if session is None:
        return error("session not found: " + str(session_id))

    target_agent = input_data.get("target_agent")

    orchestrator = MultiAgentOrchestrator()
    result = orchestrator.inject_message(
        session=session,
        message=message,
        target_agent=target_agent,
    )

    if result.get("status") == "error":
        return error(result.get("error", "unknown error"))

    return ok(result)
