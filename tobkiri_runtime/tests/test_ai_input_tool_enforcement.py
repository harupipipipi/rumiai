from __future__ import annotations

import sys
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from blocks.tool.invoke import run as invoke_tool  # noqa: E402


class _FakeRegistry:
    def get(self, tool_name):
        return {"tool_id": tool_name, "name": tool_name, "schema": {}}

    def list_tools(self):
        return []


class _FakeTraceStore:
    events: list[tuple[str, dict]] = []

    def append_blocked_event(self, profile_id, event):
        self.events.append((profile_id, dict(event)))
        return {"profile_id": profile_id, "blocked": [dict(event)]}


def test_blocked_tool_call_returns_profile_error(monkeypatch) -> None:
    monkeypatch.setattr("blocks.tool.invoke.ToolRegistry", _FakeRegistry)
    monkeypatch.setattr("core_runtime.ai_input_trace_store.AiInputTraceStore", _FakeTraceStore)
    _FakeTraceStore.events.clear()

    result = invoke_tool(
        {"tool_name": "computer_use", "arguments": {"action": "noop"}},
        {
            "active_startup_profile_id": "research-profile",
            "effective_tool_allowlist": ["web_search"],
        },
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "blocked_by_profile"
    assert result["error"]["details"]["tool_id"] == "computer_use"
    assert _FakeTraceStore.events == [
        (
            "research-profile",
            {
                "event": "tool_blocked",
                "tool_id": "computer_use",
                "reason": "not_in_effective_tool_allowlist",
                "source": "defaultspack.blocks.tool.invoke",
            },
        )
    ]
