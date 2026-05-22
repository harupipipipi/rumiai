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


def _caller_requires_denied_executor():
    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=False,
        output=None,
        error="approval required",
        error_type="caller_requires_denied",
    )
    return capability_executor


def _computer_control_tool_def(tool_name):
    return {
        "tool_id": tool_name,
        "name": tool_name,
        "risk": "high",
        "requires_approval": True,
        "capability_grants": ["browser.control", "computer.control"],
        "execution": {
            "type": "rumi_function",
            "qualified_name": f"rumi_default_tools_pack:{tool_name}",
        },
    }


def test_tool_executor_denied_browser_computer_without_approval_returns_approval_request(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = _caller_requires_denied_executor()

    def fake_execute_local(self, tool_name, arguments, context):
        raise AssertionError("browser_computer must not run locally without approval")

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("browser_computer"),
        {"action": "computer.click", "payload": {"x": 10, "y": 20}},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "browser_computer"


def test_tool_executor_denied_computer_use_without_user_request_still_requires_approval(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = _caller_requires_denied_executor()

    def fake_execute_local(self, tool_name, arguments, context):
        raise AssertionError("computer_use must not run locally without approval")

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        {"action": "click", "x": 10, "y": 20},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "computer_use"


def test_tool_executor_falls_back_to_local_browser_computer_with_server_approval(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = _caller_requires_denied_executor()
    captured = {}

    def fake_execute_local(self, tool_name, arguments, context):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["context"] = context
        return {"result": "browser_computer computer.windows completed", "is_error": False, "widget": {"type": tool_name}}

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("browser_computer"),
        {"action": "computer.windows"},
        {
            "principal_id": "defaultspack",
            "capability_executor": capability_executor,
            "_tool_server_approved": True,
        },
    )

    assert result["is_error"] is False
    assert captured["tool_name"] == "browser_computer"
    assert captured["arguments"] == {"action": "computer.windows"}


def test_tool_executor_falls_back_to_local_computer_use_with_yolo_policy(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = _caller_requires_denied_executor()
    captured = {}

    def fake_execute_local(self, tool_name, arguments, context):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["context"] = context
        return {"result": "computer_use computer.context completed", "is_error": False, "widget": {"type": tool_name}}

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        {"action": "context"},
        {
            "principal_id": "defaultspack",
            "capability_executor": capability_executor,
            "profile_policy": {"yolo_mode": True},
        },
    )

    assert result["is_error"] is False
    assert captured["tool_name"] == "computer_use"
    assert captured["arguments"] == {"action": "context"}


def test_sandbox_exec_ignores_client_supplied_approval_flags(tmp_path):
    from domain.tool.executor import ToolExecutor

    result = ToolExecutor().execute(
        "sandbox_exec",
        {"command": "pwd", "approved": True, "_tool_server_approved": True},
        {"workspace_root": str(tmp_path), "_tool_server_approved": True},
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["approval_required"] is True


def test_sandbox_exec_runs_only_with_internal_tool_decision(tmp_path):
    from domain.tool.executor import ToolExecutor
    from domain.tool_policy.internal_context import seal_tool_context

    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    result = ToolExecutor().execute("sandbox_exec", {"command": "pwd"}, context)

    assert result["is_error"] is False
    assert str(tmp_path) in result["widget"]["data"]["stdout"]


def test_package_install_plan_never_executes_packages(tmp_path):
    from domain.tool.executor import ToolExecutor

    result = ToolExecutor().execute(
        "package_install_plan",
        {"manager": "pip", "packages": ["requests"]},
        {"workspace_root": str(tmp_path)},
    )

    assert result["is_error"] is False
    assert result["widget"]["data"]["executes"] is False
    assert result["widget"]["data"]["command"][-1] == "requests"


def test_connector_approval_request_redacts_secret_arguments(tmp_path):
    from domain.tool.executor import ToolExecutor

    result = ToolExecutor().execute(
        "slack_send",
        {"text": "hello", "bot_token": "xoxb-secret", "nested": {"api_key": "secret-key"}},
        {"workspace_root": str(tmp_path)},
    )

    assert result["is_error"] is False
    arguments = result["widget"]["arguments"]
    assert arguments["bot_token"] == "[redacted]"
    assert arguments["nested"]["api_key"] == "[redacted]"
    assert "xoxb-secret" not in result["result"]


def test_connector_dry_run_redacts_secret_arguments_after_internal_approval(tmp_path):
    from domain.tool.executor import ToolExecutor
    from domain.tool_policy.internal_context import seal_tool_context

    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    result = ToolExecutor().execute(
        "slack_send",
        {"text": "hello", "bot_token": "xoxb-secret", "nested": {"api_key": "secret-key"}},
        context,
    )

    assert result["is_error"] is False
    message = result["widget"]["data"]["message"]
    assert message["bot_token"] == "[redacted]"
    assert message["nested"]["api_key"] == "[redacted]"
    assert "xoxb-secret" not in result["result"]
