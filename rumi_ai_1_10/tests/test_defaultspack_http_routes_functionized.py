from __future__ import annotations

import sys
from pathlib import Path
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
