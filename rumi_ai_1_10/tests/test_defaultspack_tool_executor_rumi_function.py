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


def test_tool_executor_uses_initialized_container_capability_executor(monkeypatch):
    from domain.tool.executor import ToolExecutor

    class _FakeExecutor:
        def __init__(self):
            self._initialized = False
            self.initialize_calls = 0

        def initialize(self):
            self.initialize_calls += 1
            self._initialized = True
            return True

        def execute(self, principal_id, request):
            return SimpleNamespace(success=True, output={"result": "ok"}, error=None, error_type=None)

    class _FakeContainer:
        def __init__(self, executor):
            self._executor = executor

        def get_or_none(self, name):
            if name == "capability_executor":
                return self._executor
            return None

    fake_executor = _FakeExecutor()
    monkeypatch.setattr(
        "core_runtime.di_container.get_container",
        lambda: _FakeContainer(fake_executor),
    )

    resolved = ToolExecutor._capability_executor({})

    assert resolved is fake_executor
    assert fake_executor._initialized is True
    assert fake_executor.initialize_calls == 1


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
        error="Pack not approved: defaultspack",
        error_type="pack_not_approved",
    )
    return capability_executor


def _success_executor():
    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"result": "done", "is_error": False, "widget": None},
        error=None,
        error_type=None,
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
    assert result["widget"]["arguments"] == {"action": "computer.click", "payload": {"x": 10, "y": 20}}
    assert result["widget"]["payload"] == {"x": 10, "y": 20}
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
    assert result["widget"]["operation"] == "computer.click"
    assert result["widget"]["arguments"] == {"action": "click", "x": 10, "y": 20}
    assert result["widget"]["payload"] == {"x": 10, "y": 20}
    assert str(result["widget"]["approval_request_id"]).startswith("apr_")


def test_tool_executor_pack_not_approved_computer_use_without_approval_returns_pack_error(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = _pack_not_approved_executor()

    def fake_execute_local(self, tool_name, arguments, context):
        raise AssertionError("computer_use must not run locally without approval")

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        {"action": "apps"},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is True
    assert result["error_type"] == "pack_not_approved"
    assert result["widget"]["type"] == "tool_execution_denied"
    assert result["widget"]["tool_name"] == "computer_use"
    assert "Pack not approved" in result["result"]


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


def test_tool_executor_git_status_stays_read_only_without_approval():
    from domain.tool.executor import ToolExecutor

    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"status": "ok", "data": {"branch": "main", "clean": True}},
        error=None,
        error_type=None,
    )

    result = ToolExecutor().execute(
        "coding_git_status",
        {"workspace_root": "."},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is False
    assert result["widget"] == {"branch": "main", "clean": True}
    capability_executor.execute.assert_called_once()


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


def test_tool_executor_pack_not_approved_does_not_consume_approval_token(monkeypatch):
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RUMI_AUTO_APPROVE_LOCAL", raising=False)
    approval.reset_approval_state_for_tests()
    args = {"path": "index.html", "old": "<body>old</body>", "new": "<body>new</body>"}
    first = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def("coding_file_patch"),
        args,
        {"principal_id": "defaultspack", "capability_executor": _caller_requires_denied_executor()},
    )
    decision = approval.approve(first["widget"]["approval_request_id"])
    assert decision["approved"] is True

    monkeypatch.setattr(
        ToolExecutor,
        "_function_call_pack_approval_status",
        staticmethod(lambda capability_executor, pack_id: (False, "not_approved")),
    )
    capability_executor = _pack_not_approved_executor()
    result = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def("coding_file_patch"),
        {**args, "approval_token": decision["token"]},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is True
    assert result["widget"] == {
        "type": "tool_execution_denied",
        "tool_name": "coding_file_patch",
        "reason": "Pack not approved: defaultspack",
    }
    capability_executor.execute.assert_not_called()
    verification = approval.verify_execution_token(
        decision["token"],
        "tool.coding_file_patch",
        approval.hash_arguments(args),
        consume=False,
        pack_id="defaultspack",
    )
    assert verification.valid is True


def test_tool_executor_dev_auto_approve_retries_before_consuming_approval_token(monkeypatch):
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    monkeypatch.setenv("RUMI_ENVIRONMENT", "development")
    monkeypatch.setenv("RUMI_AUTO_APPROVE_LOCAL", "true")
    approval.reset_approval_state_for_tests()
    args = {"path": "index.html", "old": "<body>old</body>", "new": "<body>new</body>"}
    first = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def("coding_file_patch"),
        args,
        {"principal_id": "defaultspack", "capability_executor": _caller_requires_denied_executor()},
    )
    decision = approval.approve(first["widget"]["approval_request_id"])
    assert decision["approved"] is True

    capability_executor = _success_executor()
    statuses = iter([(False, "not_approved"), (True, None)])
    monkeypatch.setattr(
        ToolExecutor,
        "_function_call_pack_approval_status",
        staticmethod(lambda capability_executor, pack_id: next(statuses)),
    )
    monkeypatch.setattr(
        ToolExecutor,
        "_dev_auto_approve_pack",
        lambda self, pack_id, capability_executor=None: True,
    )

    result = ToolExecutor()._execute_rumi_function(
        _coding_write_tool_def("coding_file_patch"),
        {**args, "approval_token": decision["token"]},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["result"] == "done"
    capability_executor.execute.assert_called_once()
    verification = approval.verify_execution_token(
        decision["token"],
        "tool.coding_file_patch",
        approval.hash_arguments(args),
        consume=False,
        pack_id="defaultspack",
    )
    assert verification.valid is False
    assert verification.code == "APPROVAL_TOKEN_USED"


def test_tool_executor_mimo_company_marks_safe_rumi_api_calls_server_approved():
    from domain.tool.executor import ToolExecutor
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"result": "ok", "is_error": False, "widget": {"type": "rumi_api"}},
        error=None,
    )

    result = ToolExecutor()._execute_rumi_function(
        ToolRegistry().get("rumi_api"),
        {"action": "list_routes"},
        {
            "profile_id": "defaultspack.mimo_coding_company",
            "principal_id": "rumi_default_tools_pack",
            "capability_executor": capability_executor,
        },
    )

    assert result["result"] == "ok"
    _, request = capability_executor.execute.call_args.args
    assert request["context"]["_tool_server_approved"] is True


def test_tool_executor_mimo_company_rumi_api_denial_falls_back_to_direct_pack_call(monkeypatch):
    from domain.tool.executor import ToolExecutor
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=False,
        output=None,
        error="approval required",
        error_type="caller_requires_denied",
    )
    seen = {}

    def fake_invoke(pack_id, function_id, *, args, context):
        seen["pack_id"] = pack_id
        seen["function_id"] = function_id
        seen["args"] = args
        seen["context"] = context
        return {"status": "ok", "data": {"routes": [], "count": 0}}

    monkeypatch.setattr("core_runtime.pack_function_runtime.invoke_pack_function", fake_invoke)

    result = ToolExecutor()._execute_rumi_function(
        ToolRegistry().get("rumi_api"),
        {"action": "list_routes"},
        {
            "profile_id": "defaultspack.mimo_coding_company",
            "principal_id": "rumi_default_tools_pack",
            "capability_executor": capability_executor,
        },
    )

    assert result["is_error"] is False
    assert seen["pack_id"] == "rumi_default_tools_pack"
    assert seen["function_id"] == "rumi_api"
    assert seen["context"]["_tool_server_approved"] is True


def test_tool_executor_mimo_company_post_rumi_api_request_still_requires_approval():
    from domain.tool.executor import ToolExecutor
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None

    result = ToolExecutor()._execute_rumi_function(
        ToolRegistry().get("rumi_api"),
        {"action": "request", "method": "POST", "path": "/api/chat/conversations"},
        {
            "profile_id": "defaultspack.mimo_coding_company",
            "principal_id": "rumi_default_tools_pack",
            "capability_executor": _caller_requires_denied_executor(),
        },
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "rumi_api"


def test_tool_executor_mimo_company_todo_pack_not_approved_falls_back_locally(tmp_path):
    from domain.tool.executor import ToolExecutor
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=False,
        output=None,
        error="Pack not approved: defaultspack",
        error_type="pack_not_approved",
    )

    result = ToolExecutor()._execute_rumi_function(
        ToolRegistry().get("todo"),
        {"action": "list"},
        {
            "profile_id": "defaultspack.mimo_coding_company",
            "conversation_workspace_dir": str(tmp_path),
            "capability_executor": capability_executor,
        },
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "todo"


def test_tool_executor_todo_pack_not_approved_without_autonomy_still_requires_approval(tmp_path):
    from domain.tool.executor import ToolExecutor
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    capability_executor = MagicMock()
    capability_executor.execute.return_value = SimpleNamespace(
        success=False,
        output=None,
        error="Pack not approved: defaultspack",
        error_type="pack_not_approved",
    )

    result = ToolExecutor()._execute_rumi_function(
        ToolRegistry().get("todo"),
        {"action": "list"},
        {
            "conversation_workspace_dir": str(tmp_path),
            "capability_executor": capability_executor,
        },
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "todo"


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


def test_tool_executor_pack_not_approved_computer_use_does_not_use_approved_local_fallback(monkeypatch):
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    capability_executor = _pack_not_approved_executor()
    arguments = {"action": "apps"}
    request = approval.create_approval_request("tool.computer_use", "high", arguments)
    decision = approval.approve(request["request_id"])

    def fake_execute_local(self, tool_name, arguments, context):
        raise AssertionError("computer_use must not bypass pack approval")

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _computer_control_tool_def("computer_use"),
        arguments,
        {
            "principal_id": "defaultspack",
            "capability_executor": capability_executor,
            "tool_approval_tokens": {"computer_use": decision["token"]},
        },
    )

    assert result["is_error"] is True
    assert result["error_type"] == "pack_not_approved"
    assert result["widget"]["type"] == "tool_execution_denied"
    assert result["widget"]["tool_name"] == "computer_use"
    assert "Pack not approved" in result["result"]


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
