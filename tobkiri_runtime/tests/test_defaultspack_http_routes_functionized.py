from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_fallback_http_block_invocation_routes_through_function_bridge():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value={"status": "ok", "data": {"models": []}},
    ) as mocked:
        result = server._invoke_fallback_block("blocks.ai.models", {}, {}, {})

    assert result == {"status": "ok", "data": {"models": []}}
    mocked.assert_called_once()
    assert mocked.call_args.args[0] == "defaultspack:ai_models"
    assert mocked.call_args.kwargs["timeout_seconds"] is None


def test_safe_get_ui_catalog_bypasses_function_bridge():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        side_effect=AssertionError("bootstrap catalog GET must not wait on the function bridge"),
    ) as invoke, patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"app": {"id": "defaultspack"}}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.ui.catalog",
            {"_actual_method": "GET"},
            {},
            {},
        )

    assert result == {"status": "ok", "data": {"app": {"id": "defaultspack"}}}
    invoke.assert_not_called()
    legacy.assert_called_once()


def test_safe_get_bootstrap_timeout_returns_error_while_health_stays_green():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    def _stuck_block(*_args, **_kwargs):
        time.sleep(5)
        return {"status": "ok", "data": {}}

    started_at = time.perf_counter()
    with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SAFE_GET_TIMEOUT_SECONDS": "0.1"}), patch(
        "transport.http.invoke_block",
        side_effect=_stuck_block,
    ):
        result = server._invoke_fallback_block(
            "blocks.ui.catalog",
            {"_actual_method": "GET"},
            {},
            {},
        )
        health = server._handle_health({}, {})
    elapsed = time.perf_counter() - started_at

    assert result["status"] == "error"
    assert result["error"]["code"] == "BOOTSTRAP_API_TIMEOUT"
    assert elapsed < 1.0
    assert health["status"] == "ok"
    assert health["data"]["status"] == "healthy"


def test_safe_get_bootstrap_default_timeout_allows_cold_start_projections():
    from transport.http import DefaultsHttpServer

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RUMI_DEFAULTSPACK_SAFE_GET_TIMEOUT_SECONDS", None)
        assert DefaultsHttpServer._safe_get_fallback_timeout_seconds() == 30.0


def test_root_shell_chunk_compat_route_serves_static_asset():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._routes = []

    handler, path_params, source, path_inject, route_pattern = server._match_route(
        "GET",
        "/shell-icons.js",
    )

    assert handler == server._handle_static_file
    assert path_params == {"path": "shell-icons.js"}
    assert source == "fallback"
    assert path_inject == {}
    assert route_pattern == ""
    assert server._match_route("GET", "/shell.html") == (None, None, None, None, None)


def test_fallback_http_chat_send_uses_long_running_timeout():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value={"status": "ok", "data": {"id": "assistant-1"}},
    ) as mocked:
        result = server._invoke_fallback_block(
            "blocks.chat.send",
            {"conversation_id": "c1"},
            {},
            {},
        )

    assert result == {"status": "ok", "data": {"id": "assistant-1"}}
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["timeout_seconds"] == 300.0


def test_fallback_http_long_running_timeout_uses_direct_block_fallback():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value={
            "status": "error",
            "error": {"code": "TIMEOUT", "message": "timed out"},
        },
    ) as invoke, patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"assistant_text": "done"}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.ambient.event_submit",
            {"trigger": "pinch", "mode": "dispatch_audio", "timeout_seconds": 180},
            {},
            {},
        )

    assert result == {"status": "ok", "data": {"assistant_text": "done"}}
    invoke.assert_called_once()
    assert invoke.call_args.args[0] == "defaultspack:ambient_event_submit"
    assert invoke.call_args.kwargs["timeout_seconds"] == 180.0
    legacy.assert_called_once()


def test_agent_subagent_uses_direct_block_without_function_grant_bridge():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        side_effect=AssertionError("subagent HTTP route must not require function grants"),
    ) as invoke, patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"assistant_text": "done"}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.agent.run_subagent",
            {"task": "delegate this", "timeout_seconds": 180},
            {},
            {},
        )

    assert result == {"status": "ok", "data": {"assistant_text": "done"}}
    invoke.assert_not_called()
    legacy.assert_called_once()


def test_agent_subagent_function_route_uses_direct_block_without_function_grant_bridge():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        side_effect=AssertionError("subagent HTTP route must not require function grants"),
    ) as invoke, patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"assistant_text": "done"}},
    ) as legacy:
        result = server._invoke_function_route(
            "defaultspack:agent_run_subagent",
            {"task": "delegate this", "timeout_seconds": 180},
            {},
            {},
            fallback_block_module="blocks.agent.run_subagent",
        )

    assert result == {"status": "ok", "data": {"assistant_text": "done"}}
    invoke.assert_not_called()
    legacy.assert_called_once()


def test_agent_subagent_local_mimo_company_route_uses_profile_authority_context():
    from transport import http
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    payload = {
        http._LOCAL_UI_APPROVAL_CONTEXT_FLAG: True,
        "task": "MiMo visual QA smoke",
        "model": "xiaomi-token-plan-sgp/mimo-v2-omni",
        "profile_id": "defaultspack.mimo_coding_company",
        "company_id": "mimo-coding-company",
        "principal_id": "profile:payload-spoof",
        "authority_principal_id": "profile:payload-spoof",
    }

    with patch("transport.http.invoke_block", return_value={"status": "ok"}) as legacy:
        result = server._invoke_fallback_block(
            "blocks.agent.run_subagent",
            payload,
            {},
            {},
        )

    assert result == {"status": "ok"}
    legacy.assert_called_once()
    context = legacy.call_args.args[2]
    assert context["_tool_server_approved"] is True
    assert context["profile_id"] == "defaultspack.mimo_coding_company"
    assert context["authority_principal_id"] == "profile:defaultspack.mimo_coding_company"
    assert context["principal_id"] == "profile:defaultspack.mimo_coding_company"


def test_agent_subagent_payload_profile_is_not_promoted_without_local_ui_authority():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    payload = {
        "task": "MiMo visual QA smoke",
        "model": "xiaomi-token-plan-sgp/mimo-v2-omni",
        "profile_id": "defaultspack.mimo_coding_company",
        "company_id": "mimo-coding-company",
        "principal_id": "profile:payload-spoof",
        "authority_principal_id": "profile:payload-spoof",
    }

    with patch("transport.http.invoke_block", return_value={"status": "ok"}) as legacy:
        result = server._invoke_fallback_block(
            "blocks.agent.run_subagent",
            payload,
            {},
            {},
        )

    assert result == {"status": "ok"}
    legacy.assert_called_once()
    context = legacy.call_args.args[2]
    assert "_tool_server_approved" not in context
    assert "profile_id" not in context
    assert "authority_principal_id" not in context
    assert "principal_id" not in context


def test_agent_subagent_local_ui_does_not_promote_other_company_profile():
    from transport import http
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    payload = {
        http._LOCAL_UI_APPROVAL_CONTEXT_FLAG: True,
        "task": "MiMo visual QA smoke",
        "model": "xiaomi-token-plan-sgp/mimo-v2-omni",
        "profile_id": "defaultspack.mimo_coding_company",
        "company_id": "other-company",
    }

    with patch("transport.http.invoke_block", return_value={"status": "ok"}) as legacy:
        result = server._invoke_fallback_block(
            "blocks.agent.run_subagent",
            payload,
            {},
            {},
        )

    assert result == {"status": "ok"}
    context = legacy.call_args.args[2]
    assert context["_tool_server_approved"] is True
    assert "profile_id" not in context
    assert "authority_principal_id" not in context
    assert "principal_id" not in context


def test_long_running_grant_denied_does_not_fallback_for_chat_send():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    denied = {
        "status": "error",
        "error": {"code": "GRANT_DENIED", "message": "Permission denied"},
    }
    with patch("domain.function_runtime.bridge.invoke_function", return_value=denied), patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"unsafe": True}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.chat.send",
            {"conversation_id": "c1", "timeout_seconds": 180},
            {},
            {},
        )

    assert result == denied
    legacy.assert_not_called()


def test_fallback_http_ambient_event_uses_long_running_timeout():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value={"status": "ok", "data": {"event_id": "ambient-1"}},
    ) as mocked:
        result = server._invoke_function_route(
            "defaultspack:ambient_event_submit",
            {"trigger": "pinch", "mode": "dispatch_audio"},
            {},
            {},
            fallback_block_module="blocks.ambient.event_submit",
        )

    assert result == {"status": "ok", "data": {"event_id": "ambient-1"}}
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["timeout_seconds"] == 300.0


def test_agent_schedule_trigger_uses_schedule_timeout_budget():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value={"status": "ok", "data": {"execution_id": "sexec-1"}},
    ) as mocked:
        result = server._invoke_fallback_block(
            "blocks.agent.scheduler.trigger",
            {"schedule_id": "sched-1"},
            {},
            {},
        )

    assert result == {"status": "ok", "data": {"execution_id": "sexec-1"}}
    mocked.assert_called_once()
    assert mocked.call_args.args[0] == "defaultspack:agent_schedule_trigger"
    assert mocked.call_args.kwargs["timeout_seconds"] == 1800.0
    assert mocked.call_args.args[1]["timeout_seconds"] == 1800.0


def test_sandbox_api_function_route_uses_in_process_block_for_runtime_operations():
    from transport import http
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch("domain.function_runtime.bridge.invoke_function") as invoke, patch(
        "transport.http.invoke_block",
        return_value={
            "status": "ok",
            "data": {"operation_id": "runtime-ensure-1", "status": "running"},
        },
    ) as legacy:
        result = server._invoke_function_route(
            "managed_runtime_ensure",
            {
                http._LOCAL_UI_APPROVAL_CONTEXT_FLAG: True,
                "_handler": "runtime_ensure",
                "provider_id": "windows_wsl",
            },
            {},
            {},
            fallback_block_module="blocks.sandbox.api",
        )

    assert result == {
        "status": "ok",
        "data": {"operation_id": "runtime-ensure-1", "status": "running"},
    }
    invoke.assert_not_called()
    legacy.assert_called_once()
    assert legacy.call_args.args[0] == "blocks.sandbox.api"
    assert legacy.call_args.args[1] == {
        "_handler": "runtime_ensure",
        "provider_id": "windows_wsl",
    }
    assert legacy.call_args.args[2]["_tool_server_approved"] is True
    assert legacy.call_args.args[2]["source"] == "defaultspack_local_ui"
    assert legacy.call_args.args[2]["_defaultspack_http_route_adapter"] is True


def test_registry_sandbox_api_function_route_uses_in_process_block():
    from transport import http
    from transport.http import DefaultsHttpServer

    class Facade:
        def get_interface(self, key, strategy=None):
            if key != "io.http.route":
                return None
            return [
                {
                    "method": "POST",
                    "pattern": "/api/runtime/ensure",
                    "function_id": "managed_runtime_ensure",
                    "block_module": "blocks.sandbox.api",
                    "default_args": {"_handler": "runtime_ensure"},
                    "sensitive": True,
                    "local_only": True,
                }
            ]

    server = DefaultsHttpServer(Facade())
    server._build_context = lambda: {"request_id": "req-1"}
    handler, params, source, path_inject, route_pattern = server._match_route(
        "POST",
        "/api/runtime/ensure",
    )

    assert source == "registry"
    assert path_inject == {}
    assert route_pattern == "/api/runtime/ensure"
    assert getattr(handler, "_defaultspack_flow_route_handler", False) is True

    with patch("domain.function_runtime.bridge.invoke_function") as invoke, patch(
        "transport.http.invoke_block",
        return_value={
            "status": "ok",
            "data": {"operation_id": "runtime-ensure-1", "status": "running"},
        },
    ) as legacy:
        result = handler(
            {
                http._LOCAL_UI_APPROVAL_CONTEXT_FLAG: True,
                "provider_id": "windows_wsl",
            },
            params,
        )

    assert result == {
        "status": "ok",
        "data": {"operation_id": "runtime-ensure-1", "status": "running"},
    }
    invoke.assert_not_called()
    legacy.assert_called_once()
    assert legacy.call_args.args[0] == "blocks.sandbox.api"
    assert legacy.call_args.args[1] == {
        "_handler": "runtime_ensure",
        "_method": "POST",
        "provider_id": "windows_wsl",
    }
    assert legacy.call_args.args[2]["_tool_server_approved"] is True
    assert legacy.call_args.args[2]["source"] == "defaultspack_local_ui"
    assert legacy.call_args.args[2]["_defaultspack_http_route_adapter"] is True


def test_fallback_http_explicit_timeout_overrides_default():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value={"status": "ok", "data": {"id": "assistant-1"}},
    ) as mocked:
        result = server._invoke_fallback_block(
            "blocks.chat.send",
            {"conversation_id": "c1", "timeout_seconds": 45},
            {},
            {},
        )

    assert result == {"status": "ok", "data": {"id": "assistant-1"}}
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["timeout_seconds"] == 45.0


def test_fallback_http_block_invocation_preserves_legacy_fallback_on_missing_registry():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    with patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value={
            "status": "error",
            "error": {
                "code": "FUNCTION_REGISTRY_UNAVAILABLE",
                "message": "not ready",
            },
        },
    ), patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"legacy": True}},
    ) as legacy:
        result = server._invoke_fallback_block("blocks.ai.models", {}, {}, {})

    assert result == {"status": "ok", "data": {"legacy": True}}
    legacy.assert_called_once()


def test_fallback_http_safe_get_uses_block_on_function_call_permission_denied():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    denied = {
        "status": "error",
        "error": {
            "code": "PERMISSION_DENIED",
            "message": "Permission denied: function.call",
        },
    }
    with patch("domain.function_runtime.bridge.invoke_function", return_value=denied), patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"safe": True}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.chat.list_conversations",
            {"_actual_method": "GET"},
            {},
        )

    assert result == {"status": "ok", "data": {"safe": True}}
    legacy.assert_called_once()


def test_fallback_http_permission_denied_does_not_fallback_for_post():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    denied = {
        "status": "error",
        "error": {
            "code": "PERMISSION_DENIED",
            "message": "Permission denied: function.call",
        },
    }
    with patch("domain.function_runtime.bridge.invoke_function", return_value=denied), patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"unsafe": True}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.chat.create_conversation",
            {"_actual_method": "POST"},
            {},
        )

    assert result == denied
    legacy.assert_not_called()


def test_fallback_http_permission_denied_does_not_fallback_for_other_permission():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    denied = {
        "status": "error",
        "error": {
            "code": "PERMISSION_DENIED",
            "message": "Permission denied: tool.invoke",
        },
    }
    with patch("domain.function_runtime.bridge.invoke_function", return_value=denied), patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"unsafe": True}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.tool.list",
            {"_actual_method": "GET"},
            {},
        )

    assert result == denied
    legacy.assert_not_called()


def test_fallback_http_external_sources_get_does_not_use_legacy_fallback():
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    denied = {
        "status": "error",
        "error": {
            "code": "PERMISSION_DENIED",
            "message": "Permission denied: function.call",
        },
    }
    with patch("domain.function_runtime.registry.function_id_for_block_module", return_value="external_sources"), patch(
        "domain.function_runtime.bridge.invoke_function",
        return_value=denied,
    ), patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"sources": []}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.external.sources",
            {"_actual_method": "GET"},
            {},
        )

    assert result == denied
    legacy.assert_not_called()


def test_fallback_http_dev_auto_approve_retries_pack_not_approved_post(monkeypatch):
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}
    monkeypatch.setenv("RUMI_ENVIRONMENT", "development")
    monkeypatch.setenv("RUMI_AUTO_APPROVE_LOCAL", "true")

    approved = []

    class FakeApprovalManager:
        def scan_packs(self):
            return ["defaultspack"]

        def approve(self, pack_id):
            approved.append(pack_id)
            return SimpleNamespace(success=True)

    denied = {
        "status": "error",
        "error": {
            "code": "PACK_NOT_APPROVED",
            "message": "Pack not approved: defaultspack",
        },
    }
    ok = {"status": "ok", "data": {"id": "conversation-1"}}
    with patch(
        "domain.function_runtime.bridge.invoke_function",
        side_effect=[denied, ok],
    ) as invoke, patch(
        "core_runtime.approval_manager.get_approval_manager",
        return_value=FakeApprovalManager(),
    ), patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"legacy": True}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.chat.create_conversation",
            {"_actual_method": "POST"},
            {},
        )

    assert result == ok
    assert invoke.call_count == 2
    assert approved == ["defaultspack"]
    legacy.assert_not_called()


def test_fallback_http_pack_not_approved_post_without_dev_auto_approve_does_not_retry(monkeypatch):
    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}
    monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RUMI_AUTO_APPROVE_LOCAL", raising=False)

    denied = {
        "status": "error",
        "error": {
            "code": "PACK_NOT_APPROVED",
            "message": "Pack not approved: defaultspack",
        },
    }
    with patch("domain.function_runtime.bridge.invoke_function", return_value=denied) as invoke, patch(
        "transport.http.invoke_block",
        return_value={"status": "ok", "data": {"unsafe": True}},
    ) as legacy:
        result = server._invoke_fallback_block(
            "blocks.chat.create_conversation",
            {"_actual_method": "POST"},
            {},
        )

    assert result == denied
    invoke.assert_called_once()
    legacy.assert_not_called()


def test_external_webhook_admin_routes_require_sensitive_http_auth():
    from transport import http

    assert http._requires_sensitive_http_auth("GET", "/api/external/tokens")
    assert http._requires_sensitive_http_auth("POST", "/api/external/tokens")

    assert http._requires_sensitive_http_auth("GET", "/api/external/sources")
    assert http._requires_sensitive_http_auth("POST", "/api/external/sources")
    assert http._requires_sensitive_http_auth("PUT", "/api/external/sources")
    assert http._requires_sensitive_http_auth("DELETE", "/api/external/sources")

    assert not http._requires_sensitive_http_auth("GET", "/api/external/templates")
    assert http._requires_sensitive_http_auth("POST", "/api/external/templates")

    assert http._requires_sensitive_http_auth("GET", "/api/webhooks/endpoints")
    assert http._requires_sensitive_http_auth("POST", "/api/webhooks/endpoints")
    assert http._requires_sensitive_http_auth("PUT", "/api/webhooks/endpoints/test-webhook")
    assert http._requires_sensitive_http_auth("DELETE", "/api/webhooks/endpoints/test-webhook")
    assert http._requires_sensitive_http_auth("POST", "/api/webhooks/endpoints/test-webhook/test")

    assert http._requires_sensitive_http_auth("GET", "/api/webhooks/public-urls")
    assert http._requires_sensitive_http_auth("POST", "/api/webhooks/public-urls")
    assert http._requires_sensitive_http_auth("DELETE", "/api/webhooks/public-urls/cfqt_123")

    assert not http._requires_sensitive_http_auth("POST", "/api/webhooks/inbound/test-webhook")


def test_recording_routes_require_sensitive_http_auth_and_cors():
    from transport import http

    assert http._requires_sensitive_http_auth("GET", "/api/recording/devices")
    assert http._requires_sensitive_http_auth("POST", "/api/recording/capture")
    assert http._is_sensitive_http_path("/api/recording/devices")
    assert http._is_sensitive_http_path("/api/recording/capture")


def test_external_webhook_admin_routes_are_sensitive_for_cors():
    from transport import http

    assert http._is_sensitive_http_path("/api/webhooks/endpoints")
    assert http._is_sensitive_http_path("/api/webhooks/endpoints/test-webhook")
    assert http._is_sensitive_http_path("/api/webhooks/public-urls")
    assert http._is_sensitive_http_path("/api/webhooks/public-urls/cfqt_123")
    assert http._is_sensitive_http_path("/api/external/sources")
    assert http._is_sensitive_http_path("/api/external/templates")

    assert not http._is_sensitive_http_path("/api/webhooks/inbound/test-webhook")


def test_high_risk_defaultspack_local_routes_use_sensitive_cors():
    from transport import http

    for path in (
        "/api/tools/browser-computer",
        "/api/tools/invoke",
        "/api/tools/create",
        "/api/tools/mcp/connect",
        "/api/tools/example",
        "/api/tools/example/permissions",
        "/api/container",
        "/api/container/abc/exec",
        "/api/container/abc/screenshot",
        "/api/container/task/job-1/abort",
    ):
        assert http._is_sensitive_http_path(path)

    assert not http._is_sensitive_http_path("/api/tools/browser-companion/bridge/poll")


def test_human_operator_canvas_routes_are_sensitive_for_cors_without_bearer_auth():
    from transport import http

    page_path = "/api/human-operator/conversations/c1/sessions/s1"
    message_path = "/api/human-operator/conversations/c1/sessions/s1/messages"

    assert http._is_sensitive_http_path(page_path)
    assert http._is_sensitive_http_path(message_path)
    assert not http._requires_sensitive_http_auth("GET", page_path)
    assert not http._requires_sensitive_http_auth("POST", message_path)


def test_high_risk_defaultspack_local_routes_require_loopback_origin_and_csrf():
    from domain.safety.local_guard import require_local_guard

    assert require_local_guard(
        "/api/tools/browser-computer",
        "POST",
        {},
        ("203.0.113.10", 4242),
    ) == (403, "sensitive local route requires a loopback client", "LOCAL_ONLY_REQUIRED")
    assert require_local_guard(
        "/api/tools/create",
        "POST",
        {"Origin": "https://example.com", "X-Rumi-CSRF": "1"},
        ("127.0.0.1", 4242),
    ) == (403, "origin not allowed for sensitive local route", "ORIGIN_DENIED")
    assert require_local_guard(
        "/api/container/abc/exec",
        "POST",
        {"Origin": "http://localhost:8766"},
        ("127.0.0.1", 4242),
    ) == (403, "CSRF header required for sensitive local mutation", "CSRF_REQUIRED")
    assert require_local_guard(
        "/api/container/abc/exec",
        "POST",
        {"Origin": "http://localhost:8766", "X-Rumi-CSRF": "csrf"},
        ("127.0.0.1", 4242),
    ) is None
