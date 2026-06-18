from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _FakeAuthorityService:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.approve_kwargs = []

    def approve_request(
        self,
        request_id,
        *,
        scope="once",
        config=None,
        expires_in_seconds=None,
        related_permissions=None,
        ui_operator=None,
    ):
        self.calls.append((request_id, scope, config, expires_in_seconds))
        self.approve_kwargs.append({
            "related_permissions": related_permissions,
            "ui_operator": ui_operator,
        })
        return self.result

    def deny_request(self, request_id, *, reason="", persist=False, ui_operator=None):
        self.calls.append((request_id, reason, persist))
        return self.result

    def list_requests(self, status="all"):
        self.calls.append((status,))
        return self.result


def test_authority_http_approve_returns_decision(monkeypatch):
    from blocks.authority import requests

    service = _FakeAuthorityService({
        "success": True,
        "approved": True,
        "request_id": "auth_1",
        "scope": "once",
        "token": "approval-token",
    })
    monkeypatch.setattr(requests, "_authority_service", lambda: service)

    result = requests.run({
        "action": "approve",
        "request_id": "auth_1",
        "scope": "once",
        "config": {"provider_ids": ["opencode-go"]},
        "expires_in_seconds": "60",
    })

    assert result["status"] == "ok"
    assert result["data"]["approved"] is True
    assert result["data"]["token"] == "approval-token"
    assert service.calls == [("auth_1", "once", {"provider_ids": ["opencode-go"]}, 60)]


def test_authority_http_transport_approve_passes_related_permissions_and_ui_operator(monkeypatch):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    service = _FakeAuthorityService({
        "success": True,
        "approved": True,
        "request_id": "auth_1",
        "scope": "session",
        "token": "approval-token",
    })
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    ui_operator = {
        "kind": "ui_operator",
        "request_id": "auth_1",
        "nonce": "nonce-1",
    }

    result = server._handle_authority_approve(
        {
            "scope": "session",
            "config": {"provider_ids": ["opencode-go"]},
            "expires_in_seconds": 60,
            "related_permissions": ["api_key.use", 123],
            "ui_operator": ui_operator,
            "approved": True,
        },
        {"request_id": "auth_1"},
    )

    assert result["status"] == "ok"
    assert result["data"]["approved"] is True
    assert service.calls == [("auth_1", "session", {"provider_ids": ["opencode-go"]}, 60)]
    assert service.approve_kwargs == [{
        "related_permissions": ["api_key.use", "123"],
        "ui_operator": ui_operator,
    }]


def test_authority_browser_ui_operator_endpoint_is_disabled_without_token(monkeypatch):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    monkeypatch.delenv("RUMI_AUTHORITY_BROWSER_TEST_TOKEN", raising=False)
    server = DefaultsHttpServer.__new__(DefaultsHttpServer)

    result = server._handle_authority_browser_ui_operator({"request_id": "auth_1"}, {})

    assert result["status"] == "error"
    assert result["_http_status"] == 404
    assert result["error"]["code"] == "AUTHORITY_BROWSER_TEST_DISABLED"


def test_authority_browser_ui_operator_endpoint_requires_valid_token(monkeypatch):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    monkeypatch.setenv("RUMI_AUTHORITY_BROWSER_TEST_TOKEN", "browser-secret")
    server = DefaultsHttpServer.__new__(DefaultsHttpServer)

    missing = server._handle_authority_browser_ui_operator({"request_id": "auth_1"}, {})
    invalid = server._handle_authority_browser_ui_operator(
        {
            "request_id": "auth_1",
            "_headers": {"X-Rumi-Approval-Browser-Token": "wrong"},
        },
        {},
    )

    assert missing["status"] == "error"
    assert missing["_http_status"] == 401
    assert missing["error"]["code"] == "AUTHORITY_BROWSER_TOKEN_REQUIRED"
    assert invalid["status"] == "error"
    assert invalid["_http_status"] == 403
    assert invalid["error"]["code"] == "AUTHORITY_BROWSER_TOKEN_INVALID"


def test_authority_browser_ui_operator_endpoint_mints_signed_context(monkeypatch):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer
    from core_runtime.authority.ui_operator import verify_ui_operator

    monkeypatch.setenv("RUMI_AUTHORITY_BROWSER_TEST_TOKEN", "browser-secret")
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-signing-secret-" + ("x" * 32))
    server = DefaultsHttpServer.__new__(DefaultsHttpServer)

    result = server._handle_authority_browser_ui_operator(
        {
            "request_id": "auth_1",
            "browser_approval_token": "browser-secret",
        },
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["request_id"] == "auth_1"
    ui_operator = result["data"]["ui_operator"]
    verified, reason, normalized = verify_ui_operator(ui_operator, request_id="auth_1")
    assert verified is True, reason
    assert normalized["request_id"] == "auth_1"


def test_authority_http_errors_preserve_status(monkeypatch):
    from blocks.authority import requests

    service = _FakeAuthorityService({
        "success": False,
        "error": "Authority request not found",
        "status_code": 404,
    })
    monkeypatch.setattr(requests, "_authority_service", lambda: service)

    result = requests.run({"action": "approve", "request_id": "missing"})

    assert result["status"] == "error"
    assert result["_http_status"] == 404
    assert result["error"]["code"] == "AUTHORITY_APPROVAL_FAILED"
