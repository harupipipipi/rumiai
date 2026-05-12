from __future__ import annotations

import sys
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


def test_external_webhook_admin_routes_are_sensitive_for_cors():
    from transport import http

    assert http._is_sensitive_http_path("/api/webhooks/endpoints")
    assert http._is_sensitive_http_path("/api/webhooks/endpoints/test-webhook")
    assert http._is_sensitive_http_path("/api/webhooks/public-urls")
    assert http._is_sensitive_http_path("/api/webhooks/public-urls/cfqt_123")
    assert http._is_sensitive_http_path("/api/external/sources")
    assert http._is_sensitive_http_path("/api/external/templates")

    assert not http._is_sensitive_http_path("/api/webhooks/inbound/test-webhook")
