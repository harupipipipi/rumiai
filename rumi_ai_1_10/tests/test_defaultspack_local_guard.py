from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_sensitive_coding_http_path_uses_local_guard():
    from transport.http import _RequestHandler, _is_sensitive_http_path

    for path in (
        "/api/coding/files",
        "/api/coding/files/read",
        "/api/coding/files/search",
        "/api/coding/files/diff",
        "/api/coding/files/write",
    ):
        assert _is_sensitive_http_path(path) is True

    handler = _RequestHandler.__new__(_RequestHandler)
    handler.headers = {"Origin": "https://example.test"}
    handler.client_address = ("127.0.0.1", 54321)

    assert handler._sensitive_request_error("POST", "/api/coding/files/write") == (
        403,
        "origin not allowed for sensitive local route",
        "ORIGIN_DENIED",
    )
    assert handler._sensitive_request_error("POST", "/api/coding/files/read") == (
        403,
        "origin not allowed for sensitive local route",
        "ORIGIN_DENIED",
    )
    assert handler._sensitive_request_error("GET", "/api/coding/files") == (
        403,
        "origin not allowed for sensitive local route",
        "ORIGIN_DENIED",
    )


def test_sensitive_coding_http_path_requires_csrf_for_local_origin():
    from transport.http import _RequestHandler

    handler = _RequestHandler.__new__(_RequestHandler)
    handler.headers = {"Origin": "http://localhost:8766"}
    handler.client_address = ("127.0.0.1", 54321)

    assert handler._sensitive_request_error("POST", "/api/coding/terminal/exec") == (
        403,
        "CSRF header required for sensitive local mutation",
        "CSRF_REQUIRED",
    )
    assert handler._sensitive_request_error("POST", "/api/authority/requests/auth_1/approve") == (
        403,
        "CSRF header required for sensitive local mutation",
        "CSRF_REQUIRED",
    )

    handler.headers = {"Origin": "http://localhost:8766", "X-Rumi-CSRF": "1"}
    assert handler._sensitive_request_error("POST", "/api/coding/terminal/exec") is None
    assert (
        handler._sensitive_request_error("POST", "/api/authority/requests/auth_1/approve") is None
    )

    handler.headers = {"origin": "http://localhost:8766", "x-rumi-csrf": "1"}
    assert handler._sensitive_request_error("POST", "/api/coding/terminal/exec") is None


def test_git_branch_post_is_guarded_but_get_remains_read_only():
    from transport.http import _RequestHandler, _is_sensitive_http_path

    assert _is_sensitive_http_path("/api/coding/git/branch") is True

    handler = _RequestHandler.__new__(_RequestHandler)
    handler.headers = {"Origin": "http://localhost:8766"}
    handler.client_address = ("127.0.0.1", 54321)

    assert handler._sensitive_request_error("GET", "/api/coding/git/branch") is None
    assert handler._sensitive_request_error("POST", "/api/coding/git/branch") == (
        403,
        "CSRF header required for sensitive local mutation",
        "CSRF_REQUIRED",
    )


def test_cockpit_sensitive_reads_are_guarded():
    from transport.http import _RequestHandler, _is_sensitive_http_path

    sensitive_reads = [
        "/api/coding/approvals",
        "/api/authority/requests",
        "/api/authority/test/request",
        "/api/browser/artifacts",
        "/api/coding/agent/sessions/status",
        "/api/coding/agent/sessions/merge-report",
    ]
    for path in sensitive_reads:
        assert _is_sensitive_http_path(path) is True

    handler = _RequestHandler.__new__(_RequestHandler)
    handler.headers = {"Origin": "https://example.test"}
    handler.client_address = ("127.0.0.1", 54321)

    assert handler._sensitive_request_error("GET", "/api/coding/approvals") == (
        403,
        "origin not allowed for sensitive local route",
        "ORIGIN_DENIED",
    )

    handler.headers = {"Origin": "http://localhost:8766"}
    assert handler._sensitive_request_error("GET", "/api/coding/approvals") is None


def test_parameterized_workspace_mutations_are_guarded():
    from domain.safety.local_guard import is_sensitive_coding_path

    assert is_sensitive_coding_path("/api/coding/workspaces/ws-1", "PUT") is True
    assert is_sensitive_coding_path("/api/coding/workspaces/ws-1/select", "POST") is True
    assert is_sensitive_coding_path("/api/coding/workspaces/ws-1/trust", "POST") is True
    assert is_sensitive_coding_path("/api/coding/workspaces/ws-1", "GET") is False


def test_dynamic_tool_post_routes_are_guarded():
    from domain.safety.local_guard import require_local_guard
    from transport.http import _is_sensitive_http_path

    assert _is_sensitive_http_path("/api/tools/example") is True
    assert require_local_guard(
        "/api/tools/example",
        "POST",
        {"Origin": "http://localhost:8766"},
        ("127.0.0.1", 54321),
    ) == (
        403,
        "CSRF header required for sensitive local mutation",
        "CSRF_REQUIRED",
    )


def test_route_metadata_sensitive_reads_server_route_table():
    from transport.http import _RequestHandler

    def handler(request_data, path_params):
        return {"ok": True, "request_data": request_data, "path_params": path_params}

    handler.__rumi_route_sensitive__ = True
    request_handler = _RequestHandler.__new__(_RequestHandler)
    request_handler.server_ref = SimpleNamespace(
        _routes=[
            (
                "POST",
                re.compile("^/api/template/sensitive$"),
                handler,
                "registry",
                {},
                "/api/template/sensitive",
            )
        ]
    )

    assert request_handler._route_metadata_sensitive("POST", "/api/template/sensitive") is True
    assert request_handler._route_metadata_sensitive("GET", "/api/template/sensitive") is False


def test_ambient_browser_qa_token_can_submit_pre_auth_event(monkeypatch):
    from transport.http import _RequestHandler

    def handler(request_data, path_params):
        return {"ok": True, "request_data": request_data, "path_params": path_params}

    handler.__rumi_route_pre_auth__ = True
    request_handler = _RequestHandler.__new__(_RequestHandler)
    request_handler.client_address = ("127.0.0.1", 54321)
    request_handler.server_ref = SimpleNamespace(
        _routes=[
            (
                "POST",
                re.compile("^/api/ambient/events$"),
                handler,
                "registry",
                {},
                "/api/ambient/events",
            )
        ]
    )

    monkeypatch.setenv("RUMI_API_TOKEN", "local-secret")
    monkeypatch.setenv("RUMI_AUTHORITY_BROWSER_TEST_TOKEN", "browser-secret")

    request_handler.headers = {
        "Origin": "http://localhost:8766",
        "X-Rumi-CSRF": "1",
        "X-Rumi-Approval-Browser-Token": "browser-secret",
    }
    assert request_handler._sensitive_request_error("POST", "/api/ambient/events") is None

    request_handler.headers = {
        "Origin": "http://localhost:8766",
        "X-Rumi-CSRF": "1",
        "X-Rumi-Approval-Browser-Token": "wrong",
    }
    assert request_handler._sensitive_request_error("POST", "/api/ambient/events") == (
        401,
        "local auth token required",
        "AUTH_REQUIRED",
    )

    request_handler.headers = {
        "Origin": "http://localhost:8766",
        "X-Rumi-Approval-Browser-Token": "browser-secret",
    }
    assert request_handler._sensitive_request_error("POST", "/api/ambient/events") == (
        403,
        "CSRF header required for sensitive integration mutation",
        "CSRF_REQUIRED",
    )


def test_ambient_browser_qa_context_flag_becomes_tool_server_approval():
    from transport.http import _AMBIENT_BROWSER_QA_CONTEXT_FLAG, _apply_ambient_browser_qa_context

    context = {}
    payload = {_AMBIENT_BROWSER_QA_CONTEXT_FLAG: True, "input_text": "hello"}

    _apply_ambient_browser_qa_context(context, payload)

    assert payload == {"input_text": "hello"}
    assert context["_tool_server_approved"] is True
    assert context["source"] == "ambient_browser_qa"
    assert context["approval_id"] == "ambient_browser_qa"


def test_ambient_browser_qa_context_reaches_function_routes(monkeypatch):
    from domain.function_runtime import bridge
    from transport.http import DefaultsHttpServer, _AMBIENT_BROWSER_QA_CONTEXT_FLAG

    captured = {}

    def fake_invoke_function(function_name, args, context, **kwargs):
        captured["function_name"] = function_name
        captured["args"] = dict(args)
        captured["context"] = dict(context)
        captured["kwargs"] = dict(kwargs)
        return {"status": "ok", "data": {"ok": True}}

    monkeypatch.setattr(bridge, "invoke_function", fake_invoke_function)
    server = DefaultsHttpServer.__new__(DefaultsHttpServer)

    result = server._invoke_function_route(
        "ambient_event_submit",
        {_AMBIENT_BROWSER_QA_CONTEXT_FLAG: True, "input_text": "hello"},
        {},
    )

    assert result["status"] == "ok"
    assert captured["function_name"] == "ambient_event_submit"
    assert captured["args"] == {"input_text": "hello"}
    assert captured["context"]["_tool_server_approved"] is True
    assert captured["context"]["source"] == "ambient_browser_qa"


def test_self_improvement_routes_are_guarded_as_sensitive_local_routes():
    from domain.safety.local_guard import require_local_guard
    from transport.http import _RequestHandler, _is_sensitive_http_path

    sensitive_paths = [
        "/api/agent/self-improvement/status",
        "/api/agent/self-improvement/run",
        "/api/agent/self-improvement/report",
    ]
    for path in sensitive_paths:
        assert _is_sensitive_http_path(path) is True
        assert require_local_guard(
            path,
            "POST",
            {"Origin": "https://example.test"},
            ("127.0.0.1", 54321),
        ) == (
            403,
            "origin not allowed for sensitive local route",
            "ORIGIN_DENIED",
        )

    handler = _RequestHandler.__new__(_RequestHandler)
    handler.headers = {"Origin": "http://localhost:8766"}
    handler.client_address = ("127.0.0.1", 54321)

    assert handler._sensitive_request_error("POST", "/api/agent/self-improvement/status") == (
        403,
        "CSRF header required for sensitive local mutation",
        "CSRF_REQUIRED",
    )

    handler.headers = {"Origin": "http://localhost:8766", "X-Rumi-CSRF": "1"}
    assert handler._sensitive_request_error("POST", "/api/agent/self-improvement/status") is None


def test_memory_memo_routes_are_guarded_from_cross_origin_access():
    from domain.safety.local_guard import require_local_guard
    from transport.http import (
        _RequestHandler,
        _is_sensitive_http_path,
        _requires_sensitive_http_auth,
    )

    memo_paths = [
        "/api/memory/memo/folders",
        "/api/memory/memo/folders/personalization",
        "/api/memory/memo/notes",
        "/api/memory/memo/notes/note-1",
    ]
    for path in memo_paths:
        assert _is_sensitive_http_path(path) is True
        assert _requires_sensitive_http_auth("GET", path) is False

    assert require_local_guard(
        "/api/memory/memo/notes",
        "GET",
        {"Origin": "https://example.test"},
        ("127.0.0.1", 54321),
    ) == (
        403,
        "origin not allowed for sensitive local route",
        "ORIGIN_DENIED",
    )
    assert require_local_guard(
        "/api/memory/memo/notes",
        "POST",
        {"Origin": "http://localhost:8766"},
        ("127.0.0.1", 54321),
    ) == (
        403,
        "CSRF header required for sensitive local mutation",
        "CSRF_REQUIRED",
    )

    handler = _RequestHandler.__new__(_RequestHandler)
    sent_headers = []
    handler.path = "/api/memory/memo/notes"
    handler.headers = {"Origin": "https://example.test"}
    handler.send_header = lambda name, value: sent_headers.append((name, value))

    handler._send_cors_headers()

    assert "Access-Control-Allow-Origin" not in dict(sent_headers)


def test_non_sensitive_cors_allows_generated_csrf_header():
    from transport.http import _RequestHandler

    handler = _RequestHandler.__new__(_RequestHandler)
    sent_headers = []
    handler.path = "/api/health"
    handler.headers = {}
    handler.send_header = lambda name, value: sent_headers.append((name, value))

    handler._send_cors_headers()

    allowed_headers = dict(sent_headers)["Access-Control-Allow-Headers"]
    assert "X-Rumi-CSRF" in allowed_headers


def test_audit_redacts_secrets(tmp_path, monkeypatch):
    from domain.safety.audit import audit_path, record_attempt

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    record_attempt("test.secret", "high", {"api_key": "secret", "path": "ok.txt"})

    line = audit_path().read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["arguments"]["api_key"] == "***"
    assert payload["arguments"]["path"] == "ok.txt"
