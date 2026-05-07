from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool_policy.policy import decide_tool_policy  # noqa: E402
from domain.tool_policy.risk import resolve_tool_risk  # noqa: E402


def test_tool_policy_requires_approval_for_write_risk():
    tool = {"tool_id": "write_file", "write_action": True}
    decision = decide_tool_policy(
        tool,
        {"profile_policy": {"write_actions_require_approval": True}},
        tool_name="write_file",
    )

    assert decision.allowed is True
    assert decision.action == "ask"
    assert decision.requires_approval is True


def test_tool_policy_denies_shell_when_disabled():
    tool = {"tool_id": "terminal_exec", "category": "shell"}
    decision = decide_tool_policy(tool, {"profile_policy": {"allow_shell": False}}, tool_name="terminal_exec")

    assert decision.allowed is False
    assert decision.matched_by == "allow_shell"


def test_tool_risk_recognizes_git_push():
    assert resolve_tool_risk({"tool_id": "git_push"}, "git_push") == "git_push"


def test_rumi_function_tool_uses_supplied_capability_executor():
    seen = {}

    class Response:
        success = True
        output = {"result": "ok"}
        error = None

    class FakeCapabilityExecutor:
        def execute(self, principal_id, request):
            seen["principal_id"] = principal_id
            seen["request"] = request
            return Response()

    tool_def = {
        "tool_id": "fn",
        "execution": {"type": "rumi_function", "qualified_name": "defaultspack:fn"},
        "metadata": {"source_pack_id": "defaultspack"},
    }
    result = ToolExecutor()._execute_rumi_function(
        tool_def,
        {"x": 1},
        {"_capability_executor": FakeCapabilityExecutor(), "request_id": "req_1"},
    )

    assert result["is_error"] is False
    assert seen["principal_id"] == "defaultspack"
    assert seen["request"]["type"] == "function.call"
    assert seen["request"]["qualified_name"] == "defaultspack:fn"
