from __future__ import annotations

import json
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


def test_bridge_forwards_sanitized_request_context_to_capability_executor():
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
            "defaultspack:external_io_upsert_custom_template",
            {"id": "demo"},
            {
                "request_id": "req-approved",
                "_tool_server_approved": True,
                "approval_id": "approval-1",
                "unsafe_nested": {"secret": "drop"},
            },
        )

    assert result == {"status": "ok", "data": {}}
    _principal_id, request = executor.execute.call_args.args
    assert request["context"] == {
        "request_id": "req-approved",
        "_tool_server_approved": True,
        "approval_id": "approval-1",
    }


def test_bridge_preserves_authority_context_without_extra_nested_data():
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
            {
                "request_id": "req-authority",
                "authority_principal_id": "profile:default-profile__graph:defaultspack.startup",
                "authority": {
                    "principal_id": "profile:default-profile__graph:defaultspack.startup",
                    "permission_id": "model.invoke",
                    "request_id": "auth_1",
                    "approval_token": "token-secret",
                    "approval_tokens": {
                        "api_key.use": {
                            "permission_id": "api_key.use",
                            "request_id": "auth_2",
                            "approval_token": "token-secret-2",
                            "extra": {"drop": True},
                        }
                    },
                    "unsafe_nested": {"drop": True},
                },
            },
        )

    assert result == {"status": "ok", "data": {}}
    _principal_id, request = executor.execute.call_args.args
    assert request["context"] == {
        "request_id": "req-authority",
        "authority_principal_id": "profile:default-profile__graph:defaultspack.startup",
        "authority": {
            "principal_id": "profile:default-profile__graph:defaultspack.startup",
            "permission_id": "model.invoke",
            "request_id": "auth_1",
            "approval_token": "token-secret",
            "approval_tokens": {
                "api_key.use": {
                    "permission_id": "api_key.use",
                    "request_id": "auth_2",
                    "approval_token": "token-secret-2",
                }
            },
        },
    }


def test_bridge_sanitizes_authority_approvals_list_without_raising():
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
            {
                "request_id": "req-approvals",
                "authority": {
                    "approvals": [
                        {
                            "permission_id": "terminal.execute",
                            "request_id": "auth_1",
                            "approval_token": "token-secret",
                            "extra": {"drop": True},
                        },
                        {"permission_id": "file.write", "token": "legacy-token"},
                        {"extra": {"drop": True}},
                        "drop-me",
                    ],
                },
            },
        )

    assert result == {"status": "ok", "data": {}}
    _principal_id, request = executor.execute.call_args.args
    assert request["context"] == {
        "request_id": "req-approvals",
        "authority": {
            "approvals": [
                {
                    "permission_id": "terminal.execute",
                    "request_id": "auth_1",
                    "approval_token": "token-secret",
                },
                {"permission_id": "file.write", "token": "legacy-token"},
            ]
        },
    }


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


def test_bridge_registers_template_backed_defaultspack_functions():
    from core_runtime.function_registry import FunctionRegistry
    from domain.function_runtime.bridge import ensure_defaultspack_functions_registered

    registry = FunctionRegistry()
    registered = ensure_defaultspack_functions_registered(_FakeContainer(None, registry))

    assert registered > 0
    token_entry = registry.get("defaultspack:context_token_estimate")
    external_entry = registry.get("defaultspack:external_io_template_catalog")
    assert token_entry is not None
    assert external_entry is not None
    assert token_entry.entrypoint == "template_runner.py:run"
    assert token_entry.extensions["defaultspack"]["template_runtime"] is True
    assert token_entry.extensions["defaultspack"]["block_module"] == "blocks.context.token_estimate"


def test_template_function_specs_include_only_active_template_functions(tmp_path):
    import domain.function_runtime.template_specs as template_specs

    for status in ("active", "draft", "deprecated", "disabled"):
        template_path = tmp_path / "templates" / status / "template.json"
        template_path.parent.mkdir(parents=True)
        template_path.write_text(
            json.dumps(
                {
                    "id": f"function.{status}",
                    "kind": "backend",
                    "version": "1.0.0",
                    "status": status,
                    "trust_level": "builtin",
                    "pieces": [
                        {
                            "id": "action",
                            "kind": "function",
                            "role": "action",
                            "action_id": f"{status}_template_action",
                            "block_module": "blocks.context.token_estimate",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    template_specs._template_catalog.cache_clear()
    try:
        specs = template_specs.template_function_specs(tmp_path)
        manifests = template_specs.template_function_manifests(tmp_path)
    finally:
        template_specs._template_catalog.cache_clear()

    assert "active_template_action" in specs
    assert "active_template_action" in manifests
    assert "draft_template_action" not in specs
    assert "deprecated_template_action" not in specs
    assert "disabled_template_action" not in specs


def test_capability_executor_runs_template_backed_function_entry():
    from core_runtime.capability_executor import CapabilityExecutor
    from core_runtime.function_registry import FunctionRegistry
    from domain.function_runtime.bridge import ensure_defaultspack_functions_registered

    class PermissionManager:
        def has_permission(self, principal_id, permission):
            return True

        def check_caller_requires(self, principal_id, caller_requires):
            return True

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._function_registry = FunctionRegistry()
    executor._approval_manager = MagicMock()
    executor._approval_manager.is_pack_approved_and_verified.return_value = True
    executor._permission_manager = PermissionManager()
    executor._trust_store = MagicMock()
    executor._grant_manager = MagicMock()

    ensure_defaultspack_functions_registered(_FakeContainer(executor, executor._function_registry))
    response = executor.execute(
        "defaultspack",
        {
            "type": "function.call",
            "qualified_name": "defaultspack:context_token_estimate",
            "args": {"text": "hello template executor"},
            "request_id": "req-template-executor",
        },
    )

    assert response.success is True
    assert response.output["status"] == "ok"
    assert response.output["data"]["text_length"] == len("hello template executor")
    assert response.output["data"]["estimated_tokens"] > 0


def test_dispatcher_runs_template_backed_function_piece():
    import domain.function_runtime.dispatcher as dispatcher

    result = dispatcher.run_defaultspack_function(
        "context_token_estimate",
        {"text": "hello from a template-backed function"},
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["text_length"] == len("hello from a template-backed function")
    assert result["data"]["estimated_tokens"] > 0


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
