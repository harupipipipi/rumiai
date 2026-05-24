from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _FakeContainer:
    def __init__(self, executor, registry=None):
        self.executor = executor
        self.registry = registry

    def get_or_none(self, name):
        if name == "capability_executor":
            return self.executor
        if name == "function_registry":
            return self.registry
        return None


def test_bridge_invokes_capability_executor_with_function_call():
    from domain.function_runtime.bridge import invoke_function

    executor = MagicMock()
    executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"status": "ok", "data": {"changed": True}},
        error=None,
        error_type=None,
    )

    with patch("core_runtime.di_container.get_container", return_value=_FakeContainer(executor)):
        result = invoke_function(
            "defaultspack:ai_set_thinking_level",
            {"level": "high"},
            {"principal_id": "other_pack", "request_id": "req-1"},
        )

    assert result == {"status": "ok", "data": {"changed": True}}
    executor.execute.assert_called_once()
    principal_id, request = executor.execute.call_args.args
    assert principal_id == "defaultspack"
    assert request["type"] == "function.call"
    assert request["qualified_name"] == "defaultspack:ai_set_thinking_level"
    assert request["args"] == {"level": "high"}


def test_bridge_uses_explicit_principal_for_external_pack_callers():
    from domain.function_runtime.bridge import invoke_function

    executor = MagicMock()
    executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"status": "ok", "data": {}},
        error=None,
        error_type=None,
    )

    with patch("core_runtime.di_container.get_container", return_value=_FakeContainer(executor)):
        result = invoke_function(
            "defaultspack:ai_set_thinking_level",
            {"level": "high"},
            {"principal_id": "ignored_context_pack", "request_id": "req-2"},
            principal_id="external_pack",
        )

    assert result == {"status": "ok", "data": {}}
    principal_id, request = executor.execute.call_args.args
    assert principal_id == "external_pack"
    assert request["request_id"] == "req-2"


def test_bridge_forwards_timeout_seconds_to_capability_executor():
    from domain.function_runtime.bridge import invoke_function

    executor = MagicMock()
    executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"status": "ok", "data": {}},
        error=None,
        error_type=None,
    )

    with patch("core_runtime.di_container.get_container", return_value=_FakeContainer(executor)):
        result = invoke_function(
            "defaultspack:chat_send",
            {"conversation_id": "c1"},
            {"request_id": "req-timeout"},
            timeout_seconds=120,
        )

    assert result == {"status": "ok", "data": {}}
    principal_id, request = executor.execute.call_args.args
    assert principal_id == "defaultspack"
    assert request["timeout_seconds"] == 120


def test_high_risk_defaultspack_function_rejects_unapproved_external_caller():
    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionRegistry
    from domain.function_runtime.bridge import invoke_function

    class PermissionManager:
        def __init__(self):
            self.caller_checks = []

        def has_permission(self, principal_id, permission):
            return principal_id == "defaultspack" or permission == "function.call"

        def check_caller_requires(self, principal_id, caller_requires):
            self.caller_checks.append((principal_id, list(caller_requires)))
            return False

    approval_manager = MagicMock()
    approval_manager.is_pack_approved_and_verified.return_value = True
    permission_manager = PermissionManager()

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._function_registry = FunctionRegistry()
    executor._approval_manager = approval_manager
    executor._permission_manager = permission_manager
    executor._trust_store = MagicMock()
    executor._grant_manager = MagicMock()

    container = _FakeContainer(executor, executor._function_registry)
    with patch("core_runtime.di_container.get_container", return_value=container):
        result = invoke_function(
            "defaultspack:coding_file_write",
            {"path": "notes.txt", "content": "nope"},
            {"request_id": "req-high-risk"},
            principal_id="external_pack",
        )

    assert result["status"] == "error"
    assert result["error"]["code"] == "CALLER_REQUIRES_DENIED"
    assert permission_manager.caller_checks == []


def test_dispatcher_runs_thinking_level_function(tmp_path, monkeypatch):
    from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
    import domain.function_runtime.dispatcher as dispatcher

    monkeypatch.setattr(
        dispatcher,
        "_model_runtime_service",
        lambda: ModelRuntimeSettingsService(tmp_path),
    )
    result = dispatcher.run_defaultspack_function(
        "ai_set_thinking_level",
        {"scope": "global", "level": "high"},
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["level"] == "high"


def test_dispatcher_routes_computer_drag_to_browser_computer_tool():
    import domain.function_runtime.dispatcher as dispatcher

    tool_executor = MagicMock()
    tool_executor._execute_local.return_value = {"drag_marker": {"from": {"x": 1}, "to": {"x": 2}}}

    with patch("domain.tool.executor.ToolExecutor", return_value=tool_executor):
        result = dispatcher.run_defaultspack_function(
            "computer_drag",
            {"x1": 10, "y1": 20, "x2": 30, "y2": 40, "button": "left"},
            {"request_id": "req-drag"},
        )

    assert result == {
        "status": "ok",
        "data": {"drag_marker": {"from": {"x": 1}, "to": {"x": 2}}},
    }
    tool_executor._execute_local.assert_called_once_with(
        "browser_computer",
        {
            "action": "computer.drag",
            "payload": {"x1": 10, "y1": 20, "x2": 30, "y2": 40, "button": "left"},
        },
        {"request_id": "req-drag"},
    )


def test_dispatcher_tool_function_honors_tool_filter_rejection():
    import domain.function_runtime.dispatcher as dispatcher

    result = dispatcher.run_defaultspack_function(
        "computer_drag",
        {"x1": 10, "y1": 20, "x2": 30, "y2": 40, "button": "left"},
        {
            "tool_filter_result": [
                {
                    "tool_name": "browser_computer",
                    "status": "blocked",
                    "reason_code": "model_unsupported",
                    "reason": "selected model does not support provider tool calling",
                    "required": {"model_capabilities": ["model.tool_calling"]},
                    "actual": {"model_capabilities": ["model.text"]},
                }
            ]
        },
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "MODEL_UNSUPPORTED"
    assert result["error"]["details"]["tool_name"] == "browser_computer"
