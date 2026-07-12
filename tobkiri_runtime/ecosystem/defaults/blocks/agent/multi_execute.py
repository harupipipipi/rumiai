import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.agent.multi import MultiAgentOrchestrator
from blocks.agent._state import set_multi_session


def run(input_data, context):
    """defaults.agent.multi_execute — マルチエージェントタスクを開始する。

    input_data:
        task         : str        (必須) タスク記述
        agents       : list[dict] (必須) 各エージェントの定義
                       [{name, role, model, system_prompt, tools}, ...]
        orchestration: str        (任意) "round_robin" | "directed" | "free"
        max_turns    : int        (任意) 最大ターン数
    """
    if not isinstance(input_data, dict):
        return error("input_data must be a dict")

    task = input_data.get("task")
    if not task:
        return error("task is required")

    agents = input_data.get("agents")
    if not agents or not isinstance(agents, list):
        return error("agents is required and must be a non-empty list")

    for i, agent in enumerate(agents):
        if not isinstance(agent, dict):
            return error("agents[" + str(i) + "] must be a dict")
        if not agent.get("name"):
            return error("agents[" + str(i) + "].name is required")
        if not agent.get("role"):
            return error("agents[" + str(i) + "].role is required")

    orchestration = input_data.get("orchestration", "round_robin")
    if orchestration not in ("round_robin", "directed", "free"):
        return error("orchestration must be one of: round_robin, directed, free")

    max_turns = input_data.get("max_turns", 10)
    if not isinstance(max_turns, int) or max_turns < 1:
        return error("max_turns must be a positive integer")

    orchestrator = MultiAgentOrchestrator()
    result = orchestrator.execute(
        task=task,
        agent_dicts=agents,
        orchestration=orchestration,
        max_turns=max_turns,
    )

    session_id = result.get("session_id", "")
    session = result.get("session")
    if session is not None:
        set_multi_session(session_id, session)

    output = {
        "session_id": result.get("session_id"),
        "status": result.get("status"),
        "turn_results": result.get("turn_results", []),
        "result": result.get("result"),
    }

    if result.get("status") == "error":
        return error(result.get("error", "unknown error"))

    return ok(output)
