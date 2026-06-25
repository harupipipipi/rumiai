from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_p2p_http_routes_require_sensitive_auth(monkeypatch):
    from transport.http import (
        _RequestHandler,
        _is_sensitive_http_path,
        _requires_sensitive_http_auth,
    )

    guarded_routes = [
        ("POST", "/api/p2p/peers"),
        ("PUT", "/api/p2p/peers/peer-a"),
        ("POST", "/api/p2p/identity/rotate"),
        ("POST", "/api/p2p/messages/send"),
        ("POST", "/api/integrations/p2p/events"),
    ]
    for method, path in guarded_routes:
        assert _is_sensitive_http_path(path) is True
        assert _requires_sensitive_http_auth(method, path) is True

    handler = _RequestHandler.__new__(_RequestHandler)
    handler.headers = {"Origin": "https://evil.example"}
    handler.client_address = ("127.0.0.1", 54321)

    assert handler._sensitive_request_error("POST", "/api/p2p/peers") == (
        403,
        "origin not allowed for sensitive integration route",
        "ORIGIN_DENIED",
    )

    for env_key in ("RUMI_DEFAULTSPACK_LOCAL_TOKEN", "RUMI_API_TOKEN", "RUMI_TOKEN"):
        monkeypatch.delenv(env_key, raising=False)

    handler.headers = {"Origin": "http://localhost:8766"}
    assert handler._sensitive_request_error("POST", "/api/p2p/pairing/start") == (
        403,
        "CSRF header required for sensitive integration mutation",
        "CSRF_REQUIRED",
    )

    handler.headers = {"Origin": "http://localhost:8766", "X-Rumi-CSRF": "1"}
    assert handler._sensitive_request_error("POST", "/api/p2p/pairing/start") is None

    assert handler._sensitive_request_error("POST", "/api/p2p/messages/send") == (
        403,
        "local auth token is not configured",
        "AUTH_REQUIRED",
    )

    monkeypatch.setenv("RUMI_DEFAULTSPACK_LOCAL_TOKEN", "local-secret")
    handler.headers = {"Origin": "http://localhost:8766", "Authorization": "Bearer local-secret"}
    assert handler._sensitive_request_error("POST", "/api/integrations/p2p/events") == (
        403,
        "CSRF header required for sensitive integration mutation",
        "CSRF_REQUIRED",
    )

    handler.headers = {
        "Origin": "http://localhost:8766",
        "Authorization": "Bearer local-secret",
        "X-Rumi-CSRF": "1",
    }
    assert handler._sensitive_request_error("POST", "/api/integrations/p2p/events") is None
