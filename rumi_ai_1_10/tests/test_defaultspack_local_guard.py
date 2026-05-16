from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_sensitive_coding_http_path_uses_local_guard():
    from transport.http import _RequestHandler, _is_sensitive_http_path

    assert _is_sensitive_http_path("/api/coding/files/write") is True

    handler = _RequestHandler.__new__(_RequestHandler)
    handler.headers = {"Origin": "https://example.test"}
    handler.client_address = ("127.0.0.1", 54321)

    assert handler._sensitive_request_error("POST", "/api/coding/files/write") == (
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

    handler.headers = {"Origin": "http://localhost:8766", "X-Rumi-CSRF": "1"}
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


def test_audit_redacts_secrets(tmp_path, monkeypatch):
    from domain.safety.audit import audit_path, record_attempt

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    record_attempt("test.secret", "high", {"api_key": "secret", "path": "ok.txt"})

    line = audit_path().read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["arguments"]["api_key"] == "***"
    assert payload["arguments"]["path"] == "ok.txt"
