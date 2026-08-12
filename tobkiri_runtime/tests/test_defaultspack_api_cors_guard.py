from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_defaultspack_api_rejects_cross_site_origins():
    from transport.http import _browser_api_origin_error

    assert _browser_api_origin_error(
        "GET",
        "/api/packs/defaultspack/knowledge",
        {"Origin": "https://attacker.example"},
        ("127.0.0.1", 54321),
    ) == (
        403,
        "origin not allowed for local defaultspack API",
        "ORIGIN_DENIED",
    )
    assert _browser_api_origin_error(
        "POST",
        "/api/packs/defaultspack/knowledge",
        {"Origin": "http://localhost:8766"},
        ("127.0.0.1", 54321),
    ) is None
    assert _browser_api_origin_error(
        "POST",
        "/api/packs/defaultspack/knowledge",
        {},
        ("127.0.0.1", 54321),
    ) is None


def test_browser_companion_bridge_accepts_only_canonical_extension_origins():
    from transport.http import _browser_api_origin_error

    extension_origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"

    assert _browser_api_origin_error(
        "POST",
        "/api/tools/browser-companion/bridge/exchange",
        {"Origin": extension_origin},
        ("127.0.0.1", 54321),
    ) is None
    assert _browser_api_origin_error(
        "POST",
        "/api/packs/defaultspack/knowledge",
        {"Origin": extension_origin},
        ("127.0.0.1", 54321),
    )[2] == "ORIGIN_DENIED"
    assert _browser_api_origin_error(
        "POST",
        "/api/tools/browser-companion/bridge/exchange",
        {"Origin": "chrome-extension://not-an-extension-id"},
        ("127.0.0.1", 54321),
    )[2] == "ORIGIN_DENIED"


def test_defaultspack_api_cors_does_not_allow_cross_site_origins():
    from transport.http import _RequestHandler

    handler = _RequestHandler.__new__(_RequestHandler)
    sent_headers = []
    handler.path = "/api/packs/defaultspack/knowledge"
    handler.headers = {"Origin": "https://attacker.example"}
    handler.send_header = lambda name, value: sent_headers.append((name, value))

    handler._send_cors_headers()

    assert not any(name == "Access-Control-Allow-Origin" for name, _value in sent_headers)

    sent_headers.clear()
    handler.headers = {"Origin": "http://localhost:8766"}
    handler._send_cors_headers()

    assert ("Access-Control-Allow-Origin", "http://localhost:8766") in sent_headers

    sent_headers.clear()
    extension_origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    handler.path = "/api/tools/browser-companion/bridge/exchange"
    handler.headers = {"Origin": extension_origin}
    handler._send_cors_headers()

    assert ("Access-Control-Allow-Origin", extension_origin) in sent_headers
