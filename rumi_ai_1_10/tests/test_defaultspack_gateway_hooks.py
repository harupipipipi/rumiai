from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from blocks.gateway.start import run as gateway_start  # noqa: E402
from blocks.gateway.stop import run as gateway_stop  # noqa: E402
from domain.gateway.routing import session_key  # noqa: E402
from domain.hooks.dispatcher import dispatch_hook  # noqa: E402
from domain.hooks.registry import get_hook_registry  # noqa: E402


def test_gateway_session_key_routing():
    assert session_key(agent_id="a", conversation_id="c") == "agent:a:chat:c"
    assert session_key(job_id="j") == "cron:j"
    assert session_key(webhook_id="w") == "webhook:w"
    assert session_key(agent_id="a", channel="line", user_id="u") == "agent:a:line:user:u"


def test_gateway_http_status_starts_and_stops():
    started = gateway_start({"port": 0}, {})
    try:
        assert started["status"] == "ok"
        port = started["data"]["port"]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["enabled"] is True
    finally:
        gateway_stop({}, {})


def test_hooks_dispatch_registered_callback():
    registry = get_hook_registry()
    registry.clear()
    seen = []
    registry.register("before_tool_call", lambda payload: seen.append(payload["tool_name"]))

    errors = dispatch_hook("before_tool_call", {"tool_name": "search"})

    assert errors == []
    assert seen == ["search"]
