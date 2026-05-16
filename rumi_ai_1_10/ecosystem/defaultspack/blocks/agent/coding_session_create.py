import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from blocks.agent._state import set_multi_session
from domain.agent.multi import MultiAgentOrchestrator


def run(input_data, context=None):
    if not isinstance(input_data, dict):
        return error("input_data must be a dict")
    context = context or {}
    task = input_data.get("task") or "Coding subagent session"
    agents = input_data.get("agents") or [
        {"name": "worker", "role": "coding worker", "model": input_data.get("model", "stub/default"), "tools": []}
    ]
    if not isinstance(agents, list) or not agents:
        return error("agents must be a non-empty list", code="INVALID_INPUT")
    orchestration = input_data.get("orchestration", "round_robin")
    if orchestration not in ("round_robin", "directed", "free"):
        return error("orchestration must be one of: round_robin, directed, free", code="INVALID_INPUT")
    max_turns = input_data.get("max_turns", 10)
    if not isinstance(max_turns, int) or max_turns < 1:
        return error("max_turns must be a positive integer", code="INVALID_INPUT")
    workspace_root = input_data.get("workspace_root") or context.get("workspace_root") or context.get("conversation_workspace_dir")
    workspace_id = input_data.get("workspace_id") or context.get("workspace_id")
    result = MultiAgentOrchestrator().create_session(
        task=task,
        agent_dicts=agents,
        orchestration=orchestration,
        max_turns=max_turns,
        workspace_root=workspace_root,
        workspace_id=workspace_id,
        worktree_mode=input_data.get("worktree_mode") or "isolated",
        context=context,
    )
    if result.get("status") == "error":
        return error(result.get("error", "session create failed"), code="AGENT_SESSION_CREATE_ERROR")
    session = result.get("session")
    if session is not None:
        set_multi_session(result["session_id"], session)
    return ok(
        {
            "session_id": result.get("session_id"),
            "status": result.get("status"),
            "session": result.get("result"),
            "workspace": result.get("workspace", {}),
        }
    )
