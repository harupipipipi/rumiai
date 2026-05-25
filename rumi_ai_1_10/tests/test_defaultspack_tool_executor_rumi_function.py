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


def _pack_not_approved_executor():
    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=False,
        output=None,
        error="pack not approved",
        error_type="pack_not_approved",
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


def _coding_write_tool_def(tool_name="coding_file_create"):
    return {
        "tool_id": tool_name,
        "name": tool_name,
        "risk": "high",
        "requires_approval": True,
        "capability_grants": ["file.write"],
        "execution": {
            "type": "rumi_function",
            "qualified_name": f"defaultspack:{tool_name}",
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
    assert str(result["widget"]["approval_request_id"]).startswith("apr_")


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
    assert str(result["widget"]["approval_request_id"]).startswith("apr_")


def test_tool_executor_pack_not_approved_computer_use_waits_for_approval(monkeypatch):
    from domain.tool.executor import ToolExecutor

    def fake_execute_local(self, tool_name, arguments, context):
        raise AssertionError("computer_use must not run locally before server approval")

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        {"action": "move", "x": 10, "y": 20},
        {"principal_id": "defaultspack", "capability_executor": _pack_not_approved_executor()},
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "computer_use"
    assert str(result["widget"]["approval_request_id"]).startswith("apr_")


def test_tool_executor_pack_not_approved_computer_use_runs_after_approval(monkeypatch):
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    args = {"action": "move", "x": 10, "y": 20}
    first = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        args,
        {"principal_id": "defaultspack", "capability_executor": _pack_not_approved_executor()},
    )
    decision = approval.approve(first["widget"]["approval_request_id"])
    assert decision["approved"] is True
    captured = {}

    def fake_execute_local(self, tool_name, arguments, context):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["context"] = context
        return {"result": "computer_use computer.move completed", "is_error": False, "widget": {"type": tool_name}}

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        {**args, "approval_token": decision["token"]},
        {"principal_id": "defaultspack", "capability_executor": _pack_not_approved_executor()},
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "computer_use"
    assert captured["tool_name"] == "computer_use"
    assert captured["arguments"]["approval_token"] == decision["token"]
    assert captured["context"]["_tool_server_approved"] is True


def test_tool_executor_denied_coding_function_returns_actionable_approval_request():
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    capability_executor = _caller_requires_denied_executor()

    result = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def(),
        {"path": "index.html", "content": "<html></html>"},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "coding_file_create"
    assert result["widget"]["operation"] == "tool.coding_file_create"
    assert result["widget"]["payload"] == {"path": "index.html", "content": "<html></html>"}
    assert str(result["widget"]["approval_request_id"]).startswith("apr_")


def test_tool_executor_approval_token_marks_rumi_function_context_server_approved():
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    args = {"path": "index.html", "content": "<html></html>"}
    first = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def(),
        args,
        {"principal_id": "defaultspack", "capability_executor": _caller_requires_denied_executor()},
    )
    decision = approval.approve(first["widget"]["approval_request_id"])
    assert decision["approved"] is True

    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"result": "done", "is_error": False, "widget": None},
        error=None,
    )
    result = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def(),
        {**args, "approval_token": decision["token"]},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["result"] == "done"
    _, request = capability_executor.execute.call_args.args
    assert request["context"]["_tool_server_approved"] is True


def test_tool_executor_approval_token_can_come_from_execution_context():
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    args = {"path": "index.html", "content": "<html></html>"}
    first = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def(),
        args,
        {"principal_id": "defaultspack", "capability_executor": _caller_requires_denied_executor()},
    )
    decision = approval.approve(first["widget"]["approval_request_id"])
    assert decision["approved"] is True

    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"result": "done", "is_error": False, "widget": None},
        error=None,
    )
    result = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def(),
        args,
        {
            "principal_id": "defaultspack",
            "capability_executor": capability_executor,
            "tool_approval_tokens": {"coding_file_create": decision["token"]},
        },
    )

    assert result["result"] == "done"
    _, request = capability_executor.execute.call_args.args
    assert request["context"]["_tool_server_approved"] is True


def test_context_approval_token_mismatch_requests_fresh_computer_use_approval():
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    original_args = {"action": "context"}
    first = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        original_args,
        {"principal_id": "defaultspack", "capability_executor": _caller_requires_denied_executor()},
    )
    decision = approval.approve(first["widget"]["approval_request_id"])
    assert decision["approved"] is True

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        {"action": "show_app", "app": "Google Chrome"},
        {
            "principal_id": "defaultspack",
            "capability_executor": _caller_requires_denied_executor(),
            "tool_approval_tokens": {"computer_use": decision["token"]},
        },
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "computer_use"
    assert result["widget"]["payload"] == {"action": "show_app", "app": "Google Chrome"}
    assert result["widget"]["approval_request_id"] != first["widget"]["approval_request_id"]


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


def test_tool_executor_yolo_policy_does_not_bypass_computer_use_capability_boundary(monkeypatch):
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
    assert result["widget"]["type"] == "approval_request"
    assert "tool_name" not in captured


def test_tool_executor_local_computer_use_treats_server_approval_as_yolo(monkeypatch, tmp_path):
    from domain.tool.executor import ToolExecutor
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    captured = {}

    def fake_run(self, action, payload=None, *, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = payload
        captured["yolo_mode"] = yolo_mode
        return {"action": action, "dry_run": True, "requires_approval": False, "payload": payload or {}}

    monkeypatch.setattr(BrowserComputerController, "run", fake_run)

    result = ToolExecutor()._execute_local(
        "computer_use",
        {"action": "move", "x": 12, "y": 34},
        {
            "conversation_workspace_dir": str(tmp_path),
            "principal_id": "rumi_default_tools_pack",
            "_tool_server_approved": True,
        },
    )

    assert result["is_error"] is False
    assert captured["action"] == "computer.move"
    assert captured["yolo_mode"] is True


def test_computer_use_context_adds_haze_sequence_id():
    from domain.tool.executor import _computer_use_payload_with_context_defaults

    payload = _computer_use_payload_with_context_defaults(
        "computer.key",
        {"key": "return"},
        {"run_id": "run_abc", "computer_use_target_app": "Google Chrome"},
    )

    assert payload["computer_use_haze_sequence_id"] == "run_abc"
    assert payload["app"] == "Google Chrome"


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
