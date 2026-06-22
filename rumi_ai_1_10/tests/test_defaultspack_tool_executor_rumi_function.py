from __future__ import annotations

import base64
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


def _trusted_read_only_function_tool_def():
    return {
        "tool_id": "web_search",
        "name": "web_search",
        "risk": "medium",
        "requires_approval": False,
        "category": "network",
        "action_type": "read",
        "write_action": False,
        "capability_grants": ["network.read"],
        "trusted": True,
        "source_pack_id": "rumi_default_tools_pack",
        "metadata": {
            "source_pack_id": "rumi_default_tools_pack",
            "trusted": True,
            "requires_approval": False,
            "action_type": "read",
            "category": "network",
        },
        "execution": {
            "type": "rumi_function",
            "qualified_name": "defaultspack:tool_web_search",
        },
    }


def test_tool_executor_trusted_read_only_function_bypasses_pack_approval_gate(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = _success_executor()
    monkeypatch.setattr(
        ToolExecutor,
        "_function_call_pack_approval_status",
        staticmethod(lambda capability_executor, pack_id: (False, "not_approved")),
    )

    result = ToolExecutor()._execute_rumi_function(
        _trusted_read_only_function_tool_def(),
        {"query": "today's news", "limit": 5},
        {
            "principal_id": "defaultspack",
            "capability_executor": capability_executor,
            "_tool_server_approval_token_valid": True,
        },
    )

    assert result["is_error"] is False
    assert result["result"] == "done"
    capability_executor.execute.assert_called_once()


def test_tool_executor_trusted_web_search_pack_not_approved_falls_back_locally(monkeypatch):
    from domain.tool.executor import ToolExecutor

    capability_executor = _pack_not_approved_executor()
    captured = {}

    def fake_execute_local(self, tool_name, arguments, context):
        captured["tool_name"] = tool_name
        captured["arguments"] = dict(arguments or {})
        return {"result": "local search ok", "is_error": False, "widget": {"type": "research_sources"}}

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor()._execute_rumi_function(
        _trusted_read_only_function_tool_def(),
        {"query": "today's news", "limit": 5},
        {"principal_id": "defaultspack", "capability_executor": capability_executor},
    )

    assert result["is_error"] is False
    assert result["result"] == "local search ok"
    assert captured["tool_name"] == "web_search"
    assert captured["arguments"] == {"query": "today's news", "limit": 5}


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


def test_tool_file_reader_ignores_caller_supplied_workspace_root(tmp_path):
    from domain.function_runtime.dispatcher import run_defaultspack_function

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("SECRET", encoding="utf-8")

    result = run_defaultspack_function(
        "tool_file_reader",
        {"path": "secret.txt", "workspace_root": str(outside)},
        {"workspace_root": str(workspace)},
    )

    assert result["status"] == "ok"
    assert result["data"]["is_error"] is True
    assert result["data"]["result"] == "File not found: secret.txt"
    assert result["data"]["widget"]["error"]["code"] == "FILE_NOT_FOUND"
    assert "SECRET" not in str(result)


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


def test_sandbox_exec_fails_closed_after_internal_tool_decision_until_managed_runtime_exists(tmp_path, monkeypatch):
    from domain.tool.executor import ToolExecutor
    from domain.tool import sandbox_tools
    from domain.coding.terminal import Terminal
    from domain.tool_policy.internal_context import seal_tool_context

    class MissingRuntimeApi:
        def run(self, payload, context):
            if payload.get("_handler") == "sandboxes_create":
                return {
                    "status": "error",
                    "error": {"code": "MANAGED_RUNTIME_NOT_READY", "message": "runtime not ready"},
                }
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    def forbidden_host_terminal(*args, **kwargs):
        raise AssertionError("sandbox_exec must not fall back to host Terminal.execute")

    monkeypatch.setattr(Terminal, "execute", forbidden_host_terminal)
    monkeypatch.setattr(sandbox_tools, "_sandbox_api", lambda: MissingRuntimeApi())
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    result = ToolExecutor().execute("sandbox_exec", {"command": "pwd"}, context)

    assert result["is_error"] is True
    assert result["widget"]["error"]["code"] == "MANAGED_RUNTIME_NOT_READY"
    assert result["widget"]["error"]["argv"] == ["pwd"]


def test_sandbox_exec_creates_ephemeral_sandbox_when_no_sandbox_id(tmp_path, monkeypatch):
    from domain.tool import sandbox_tools
    from domain.tool_policy.internal_context import seal_tool_context

    class FakeSandboxApi:
        def __init__(self) -> None:
            self.calls = []

        def run(self, payload, context):
            self.calls.append(payload)
            if payload.get("_handler") == "sandboxes_create":
                return {"status": "ok", "data": {"sandbox_id": "sandbox-1"}}
            if payload.get("_handler") == "sandbox_exec":
                return {"status": "ok", "data": {"sandbox_id": payload["sandbox_id"], "argv": payload["argv"]}}
            if payload.get("_handler") == "sandbox_delete":
                return {"status": "ok", "data": {"deleted": True, "sandbox_id": payload["sandbox_id"]}}
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    fake_api = FakeSandboxApi()
    monkeypatch.setattr(sandbox_tools, "_sandbox_api", lambda: fake_api)
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    result = sandbox_tools.sandbox_exec({"argv": ["pwd"], "timeout": 5}, context)

    assert result["status"] == "ok"
    assert [call["_handler"] for call in fake_api.calls] == ["sandboxes_create", "sandbox_exec", "sandbox_delete"]
    assert fake_api.calls[0]["template_id"] == "tool.ephemeral"
    assert fake_api.calls[1]["argv"] == ["pwd"]
    assert fake_api.calls[1]["timeout_ms"] == 5000


def test_sandbox_exec_rejects_shell_strings_after_internal_tool_decision(tmp_path):
    from domain.tool.executor import ToolExecutor
    from domain.tool_policy.internal_context import seal_tool_context

    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    result = ToolExecutor().execute("sandbox_exec", {"command": "echo ok && echo nope"}, context)

    assert result["is_error"] is True
    assert result["widget"]["error"]["code"] == "SANDBOX_SHELL_STRING_REJECTED"


def test_sandbox_file_patch_and_port_tools_forward_to_runtime_api(tmp_path, monkeypatch):
    from domain.tool import sandbox_tools
    from domain.tool_policy.internal_context import seal_tool_context

    class FakeSandboxApi:
        def __init__(self) -> None:
            self.calls = []

        def run(self, payload, context):
            self.calls.append(payload)
            if payload["_handler"] == "sandbox_files_apply_patch":
                return {"status": "ok", "data": {"files_written": 1}}
            if payload["_handler"] == "sandbox_port_expose":
                return {"status": "ok", "data": {"target_url": "http://127.0.0.1:3000"}}
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    fake_api = FakeSandboxApi()
    monkeypatch.setattr(sandbox_tools, "_sandbox_api", lambda: fake_api)
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    patched = sandbox_tools.sandbox_files_apply_patch(
        {"sandbox_id": "sandbox-1", "path": "app.py", "content": "print('ok')\n"},
        context,
    )
    exposed = sandbox_tools.sandbox_port_expose(
        {"sandbox_id": "sandbox-1", "port": 3000, "protocol": "http"},
        context,
    )

    assert patched["status"] == "ok"
    assert exposed["status"] == "ok"
    assert [call["_handler"] for call in fake_api.calls] == ["sandbox_files_apply_patch", "sandbox_port_expose"]
    assert fake_api.calls[0]["sandbox_id"] == "sandbox-1"
    assert fake_api.calls[0]["path"] == "app.py"
    assert fake_api.calls[1]["port"] == 3000
    assert fake_api.calls[1]["protocol"] == "http"


def test_sandbox_file_patch_and_port_tools_require_approval(tmp_path, monkeypatch):
    from domain.tool import sandbox_tools

    class UnexpectedSandboxApi:
        def run(self, payload, context):
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    monkeypatch.setattr(sandbox_tools, "_sandbox_api", lambda: UnexpectedSandboxApi())

    patch = sandbox_tools.sandbox_files_apply_patch(
        {"sandbox_id": "sandbox-1", "path": "app.py", "content": "print('ok')"},
        {"workspace_root": str(tmp_path)},
    )
    port = sandbox_tools.sandbox_port_expose(
        {"sandbox_id": "sandbox-1", "port": 3000},
        {"workspace_root": str(tmp_path)},
    )

    assert patch["is_error"] is True
    assert patch["widget"]["error"]["code"] == "SANDBOX_APPROVAL_REQUIRED"
    assert port["is_error"] is True
    assert port["widget"]["error"]["code"] == "SANDBOX_APPROVAL_REQUIRED"


def test_python_and_node_exec_code_use_coding_templates(tmp_path, monkeypatch):
    from domain.tool import sandbox_tools
    from domain.tool_policy.internal_context import seal_tool_context

    class FakeSandboxApi:
        def __init__(self) -> None:
            self.calls = []

        def run(self, payload, context):
            self.calls.append(payload)
            if payload.get("_handler") == "sandboxes_create":
                return {"status": "ok", "data": {"sandbox_id": f"{payload['template_id']}-seat"}}
            if payload.get("_handler") == "sandbox_exec":
                return {"status": "ok", "data": {"sandbox_id": payload["sandbox_id"], "argv": payload["argv"]}}
            if payload.get("_handler") == "sandbox_delete":
                return {"status": "ok", "data": {"deleted": True, "sandbox_id": payload["sandbox_id"]}}
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    fake_api = FakeSandboxApi()
    monkeypatch.setattr(sandbox_tools, "_sandbox_api", lambda: fake_api)
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    python_result = sandbox_tools.python_exec({"code": "print('ok')"}, context)
    node_result = sandbox_tools.node_exec({"code": "console.log('ok')"}, context)

    assert python_result["status"] == "ok"
    assert node_result["status"] == "ok"
    creates = [call for call in fake_api.calls if call["_handler"] == "sandboxes_create"]
    execs = [call for call in fake_api.calls if call["_handler"] == "sandbox_exec"]
    assert [call["template_id"] for call in creates] == ["coding.python", "coding.node"]
    assert execs[0]["argv"] == ["python", "-c", "print('ok')"]
    assert execs[1]["argv"] == ["node", "-e", "console.log('ok')"]


def test_python_and_node_exec_script_path_stages_file_in_sandbox(tmp_path, monkeypatch):
    from domain.tool import sandbox_tools
    from domain.tool_policy.internal_context import seal_tool_context

    (tmp_path / "scripts").mkdir()
    python_script = tmp_path / "scripts" / "hello.py"
    node_script = tmp_path / "scripts" / "hello.js"
    python_script.write_text("print('ok')\n", encoding="utf-8")
    node_script.write_text("console.log('ok')\n", encoding="utf-8")

    class FakeSandboxApi:
        def __init__(self) -> None:
            self.calls = []

        def run(self, payload, context):
            self.calls.append(payload)
            if payload.get("_handler") == "sandboxes_create":
                return {"status": "ok", "data": {"sandbox_id": f"{payload['template_id']}-seat"}}
            if payload.get("_handler") == "sandbox_files_apply_patch":
                return {"status": "ok", "data": {"files_written": 1, "sandbox_id": payload["sandbox_id"]}}
            if payload.get("_handler") == "sandbox_exec":
                return {"status": "ok", "data": {"sandbox_id": payload["sandbox_id"], "argv": payload["argv"]}}
            if payload.get("_handler") == "sandbox_delete":
                return {"status": "ok", "data": {"deleted": True, "sandbox_id": payload["sandbox_id"]}}
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    fake_api = FakeSandboxApi()
    monkeypatch.setattr(sandbox_tools, "_sandbox_api", lambda: fake_api)
    context = seal_tool_context(
        {"artifact_root": str(tmp_path), "workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    python_result = sandbox_tools.python_exec({"script_path": "scripts/hello.py", "timeout": 5}, context)
    node_result = sandbox_tools.node_exec({"script_path": "scripts/hello.js", "timeout": 6}, context)

    assert python_result["status"] == "ok"
    assert node_result["status"] == "ok"
    creates = [call for call in fake_api.calls if call["_handler"] == "sandboxes_create"]
    patches = [call for call in fake_api.calls if call["_handler"] == "sandbox_files_apply_patch"]
    execs = [call for call in fake_api.calls if call["_handler"] == "sandbox_exec"]
    deletes = [call for call in fake_api.calls if call["_handler"] == "sandbox_delete"]
    assert [call["template_id"] for call in creates] == ["coding.python", "coding.node"]
    assert patches[0]["files"][0]["path"] == "scripts/hello.py"
    assert base64.b64decode(patches[0]["files"][0]["content_base64"]).decode("utf-8") == "print('ok')\n"
    assert patches[1]["files"][0]["path"] == "scripts/hello.js"
    assert execs[0]["argv"] == ["python", "scripts/hello.py"]
    assert execs[0]["timeout_ms"] == 5000
    assert execs[1]["argv"] == ["node", "scripts/hello.js"]
    assert execs[1]["timeout_ms"] == 6000
    assert len(deletes) == 2


def test_desktop_frame_tool_returns_base64_frame_payload(monkeypatch):
    from domain.tool import desktop_tools

    class FakeSandboxApi:
        def __init__(self) -> None:
            self.calls = []

        def run(self, payload, context):
            self.calls.append((payload, context))
            assert payload["_handler"] == "desktop_frame"
            return {
                "_binary": True,
                "status_code": 200,
                "content_type": "image/png",
                "body": b"fake-png",
                "headers": {
                    "X-Rumi-Frame-Seq": "7",
                    "X-Rumi-Frame-Width": "800",
                    "X-Rumi-Frame-Height": "600",
                    "X-Rumi-Captured-At": "2026-01-01T00:00:00Z",
                },
            }

    fake_api = FakeSandboxApi()
    monkeypatch.setattr(desktop_tools, "_sandbox_api", lambda: fake_api)

    result = desktop_tools.desktop_frame({"desktop_id": "seat-1"}, {"agent_id": "agent-1"})

    assert result["status"] == "ok"
    assert result["data"]["seat_id"] == "seat-1"
    assert result["data"]["data_base64"] == "ZmFrZS1wbmc="
    assert result["data"]["frame_seq"] == 7
    assert result["data"]["width"] == 800
    assert result["data"]["height"] == 600
    assert fake_api.calls[0][0]["owner_id"] == "agent-1"


def test_desktop_control_tools_forward_owner_and_lease_token(tmp_path, monkeypatch):
    from domain.tool import desktop_tools
    from domain.tool_policy.internal_context import seal_tool_context

    class FakeSandboxApi:
        def __init__(self) -> None:
            self.calls = []

        def run(self, payload, context):
            self.calls.append(payload)
            if payload["_handler"] == "desktop_control_acquire":
                return {"status": "ok", "data": {"lease_id": "lease-1", "lease_token": "token-1"}}
            if payload["_handler"] == "desktop_control_renew":
                return {"status": "ok", "data": {"lease_id": "lease-1"}}
            if payload["_handler"] == "desktop_control_release":
                return {"status": "ok", "data": {"released": True}}
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    fake_api = FakeSandboxApi()
    monkeypatch.setattr(desktop_tools, "_sandbox_api", lambda: fake_api)
    context = seal_tool_context(
        {"workspace_root": str(tmp_path), "agent_id": "agent-1"},
        {"action": "allow", "allowed": True},
    )

    acquire = desktop_tools.desktop_control_acquire({"desktop_id": "seat-1"}, context)
    renew = desktop_tools.desktop_control_renew({"seat_id": "seat-1", "lease_token": "token-1"}, context)
    release = desktop_tools.desktop_control_release({"seat_id": "seat-1", "lease_token": "token-1"}, context)

    assert acquire["status"] == "ok"
    assert renew["status"] == "ok"
    assert release["status"] == "ok"
    assert [call["_handler"] for call in fake_api.calls] == [
        "desktop_control_acquire",
        "desktop_control_renew",
        "desktop_control_release",
    ]
    assert all(call["seat_id"] == "seat-1" for call in fake_api.calls)
    assert all(call["owner_id"] == "agent-1" for call in fake_api.calls)
    assert fake_api.calls[1]["lease_token"] == "token-1"
    assert fake_api.calls[2]["lease_token"] == "token-1"


def test_desktop_control_tools_require_approval_and_token(tmp_path, monkeypatch):
    from domain.tool import desktop_tools
    from domain.tool_policy.internal_context import seal_tool_context

    class UnexpectedSandboxApi:
        def run(self, payload, context):
            raise AssertionError(f"unexpected sandbox api call: {payload}")

    monkeypatch.setattr(desktop_tools, "_sandbox_api", lambda: UnexpectedSandboxApi())

    without_approval = desktop_tools.desktop_control_acquire({"seat_id": "seat-1"}, {"workspace_root": str(tmp_path)})
    approved_context = seal_tool_context(
        {"workspace_root": str(tmp_path), "agent_id": "agent-1"},
        {"action": "allow", "allowed": True},
    )
    missing_token = desktop_tools.desktop_control_renew({"seat_id": "seat-1"}, approved_context)

    assert without_approval["is_error"] is True
    assert without_approval["widget"]["error"]["code"] == "SANDBOX_APPROVAL_REQUIRED"
    assert missing_token["is_error"] is True
    assert missing_token["widget"]["error"]["code"] == "INVALID_INPUT"


def test_sandbox_exec_direct_call_requires_server_side_approval(tmp_path):
    from domain.tool.sandbox_tools import sandbox_exec

    result = sandbox_exec({"argv": ["pwd"]}, {"workspace_root": str(tmp_path), "_tool_server_approved": True})

    assert result["is_error"] is True
    assert result["widget"]["error"]["code"] == "SANDBOX_APPROVAL_REQUIRED"


def test_python_exec_script_path_must_stay_inside_workspace_even_when_approved(tmp_path):
    from domain.tool.sandbox_tools import python_exec
    from domain.tool_policy.internal_context import seal_tool_context

    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("print('outside')", encoding="utf-8")
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    result = python_exec({"script_path": f"../{outside.name}"}, context)

    assert result["is_error"] is True
    assert result["widget"]["error"]["code"] == "PYTHON_EXEC_FAILED"
    assert "escapes artifact root" in result["widget"]["error"]["message"]


def test_node_exec_script_path_must_stay_inside_workspace_even_when_code_is_present(tmp_path):
    from domain.tool.sandbox_tools import node_exec
    from domain.tool_policy.internal_context import seal_tool_context

    outside = tmp_path.parent / f"{tmp_path.name}-outside.js"
    outside.write_text("console.log('outside')", encoding="utf-8")
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    result = node_exec({"code": "console.log('inside')", "script_path": f"../{outside.name}"}, context)

    assert result["is_error"] is True
    assert result["widget"]["error"]["code"] == "NODE_EXEC_FAILED"
    assert "escapes artifact root" in result["widget"]["error"]["message"]


def test_python_exec_script_path_must_stay_inside_workspace_even_when_code_is_present(
    tmp_path,
    monkeypatch,
):
    from domain.tool import sandbox_tools
    from domain.tool_policy.internal_context import seal_tool_context

    outside = tmp_path.parent / f"{tmp_path.name}-outside-code.py"
    outside.write_text("print('outside')", encoding="utf-8")
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    def forbidden_sandbox_api():
        raise AssertionError(
            "python_exec must reject an escaped script_path before sandbox API calls"
        )

    monkeypatch.setattr(sandbox_tools, "_sandbox_api", forbidden_sandbox_api)

    result = sandbox_tools.python_exec(
        {"code": "print('inside')", "script_path": f"../{outside.name}"},
        context,
    )

    assert result["is_error"] is True
    assert result["widget"]["error"]["code"] == "PYTHON_EXEC_FAILED"
    assert "escapes artifact root" in result["widget"]["error"]["message"]


def test_python_and_node_exec_reject_absolute_script_paths_outside_workspace_before_runtime_api(
    tmp_path,
    monkeypatch,
):
    from domain.tool import sandbox_tools
    from domain.tool_policy.internal_context import seal_tool_context

    outside_python = tmp_path.parent / f"{tmp_path.name}-absolute.py"
    outside_node = tmp_path.parent / f"{tmp_path.name}-absolute.js"
    outside_python.write_text("print('outside')", encoding="utf-8")
    outside_node.write_text("console.log('outside')", encoding="utf-8")
    context = seal_tool_context(
        {"workspace_root": str(tmp_path)},
        {"action": "allow", "allowed": True},
    )

    def forbidden_sandbox_api():
        raise AssertionError(
            "script_path jail must reject escaped absolute paths before sandbox API calls"
        )

    monkeypatch.setattr(sandbox_tools, "_sandbox_api", forbidden_sandbox_api)

    python_result = sandbox_tools.python_exec({"script_path": str(outside_python)}, context)
    node_result = sandbox_tools.node_exec({"script_path": str(outside_node)}, context)

    assert python_result["is_error"] is True
    assert python_result["widget"]["error"]["code"] == "PYTHON_EXEC_FAILED"
    assert (
        "outside" in python_result["widget"]["error"]["message"]
        or "artifact path" in python_result["widget"]["error"]["message"]
    )
    assert node_result["is_error"] is True
    assert node_result["widget"]["error"]["code"] == "NODE_EXEC_FAILED"
    assert (
        "outside" in node_result["widget"]["error"]["message"]
        or "artifact path" in node_result["widget"]["error"]["message"]
    )


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


def test_rumi_api_manifest_and_executor_require_approval():
    import json
    from domain.tool.executor import ToolExecutor

    manifest_path = ROOT / "ecosystem" / "rumi_default_tools_pack" / "tools" / "rumi_api" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["config"]["requires_approval"] is True

    result = ToolExecutor().execute(
        "rumi_api",
        {"action": "request", "method": "GET", "path": "/api/chat/conversations"},
        {},
    )

    assert result["is_error"] is False
    assert result["widget"]["type"] == "approval_request"
    assert result["widget"]["tool_name"] == "rumi_api"
    assert result["widget"]["approval_required"] is True


def test_rumi_api_request_action_requires_approved_context(monkeypatch):
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool import rumi_api

    def fail_request(method, path, body):
        raise AssertionError("rumi_api must not call local HTTP API without approval")

    monkeypatch.setattr(rumi_api, "_request", fail_request)

    result = rumi_api.run(
        {"action": "request", "method": "GET", "path": "/api/chat/conversations"},
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["approval_required"] is True
    assert result["data"]["tool_name"] == "rumi_api"


def test_rumi_api_request_action_allows_internal_approved_context(monkeypatch):
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool import rumi_api

    seen = {}

    def fake_request(method, path, body):
        seen["method"] = method
        seen["path"] = path
        seen["body"] = body
        return {"ok": True}

    monkeypatch.setattr(rumi_api, "_request", fake_request)

    result = rumi_api.run(
        {"action": "request", "method": "GET", "path": "/api/health"},
        {"_tool_server_approved": True, "principal_id": "defaultspack"},
    )

    assert result == {"status": "ok", "data": {"ok": True}}
    assert seen == {"method": "GET", "path": "/api/health", "body": None}
