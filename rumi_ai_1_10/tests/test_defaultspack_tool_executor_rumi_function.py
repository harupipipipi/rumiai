from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_tool_executor_rumi_function_uses_supplied_capability_executor():
    from domain.tool.executor import ToolExecutor

    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"result": "done", "is_error": False, "widget": {"ok": True}},
        error=None,
    )
    tool_def = {
        "tool_id": "set_thinking_level",
        "name": "set_thinking_level",
        "execution": {
            "type": "rumi_function",
            "qualified_name": "defaultspack:ai_set_thinking_level",
        },
    }

    result = ToolExecutor()._execute_rumi_function(
        tool_def,
        {"level": "high"},
        {"principal_id": "other_pack", "capability_executor": capability_executor},
    )

    assert result["result"] == "done"
    capability_executor.execute.assert_called_once()
    principal_id, request = capability_executor.execute.call_args.args
    assert principal_id == "other_pack"
    assert request["type"] == "function.call"
    assert request["qualified_name"] == "defaultspack:ai_set_thinking_level"


def test_tool_executor_no_longer_builds_private_function_registry():
    from domain.tool.executor import ToolExecutor

    assert not hasattr(ToolExecutor, "_build_function_registry")


def test_tool_executor_falls_back_to_local_browser_computer_when_capability_requires_approval(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=False,
        output=None,
        error="approval required",
        error_type="caller_requires_denied",
    )
    captured = {}

    def fake_execute_local(self, tool_name, arguments, context):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["context"] = context
        return {"result": "browser_computer computer.windows completed", "is_error": False, "widget": {"type": tool_name}}

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)
    tool_def = {
        "tool_id": "browser_computer",
        "name": "browser_computer",
        "requires_approval": True,
        "execution": {
            "type": "rumi_function",
            "qualified_name": "rumi_default_tools_pack:browser_computer",
        },
    }

    result = ToolExecutor()._execute_rumi_function(
        tool_def,
        {"action": "computer.windows"},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is False
    assert captured["tool_name"] == "browser_computer"
    assert captured["arguments"] == {"action": "computer.windows"}
