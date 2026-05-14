from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_prefocus_computer_use_target_window_invokes_select_window_via_call_handler(monkeypatch):
    import blocks.chat.send as send  # noqa: E402

    monkeypatch.setattr(
        send,
        "connected_tool_names",
        lambda tools, runtime_profile=None, agent_id=None: {"browser_computer", "computer_use"},
    )
    monkeypatch.setattr(
        send,
        "build_tool_execution_context",
        lambda base_context, tool_name, connected: {
            "tool_name": tool_name,
            "connected_tools": sorted(connected),
            "user_requested_computer_use": base_context.get("user_requested_computer_use"),
        },
    )

    captured = {}

    def fake_call_handler(name, payload):
        captured["name"] = name
        captured["payload"] = payload
        return {"status": "ok", "data": {"selected_window": {"app": "Google Chrome", "title": "LINE Chat - Google Chrome"}}}

    result = send._prefocus_computer_use_target_window(
        available_tools=[{"name": "browser_computer"}],
        base_context={
            "user_requested_computer_use": True,
            "computer_use_target_app": "Google Chrome",
            "computer_use_target_title": "LINE",
        },
        call_handler=fake_call_handler,
    )

    assert captured["name"] == "defaults.tool.invoke"
    assert captured["payload"]["tool_name"] == "browser_computer"
    assert captured["payload"]["arguments"] == {
        "action": "computer.select_window",
        "payload": {"app": "Google Chrome", "title": "LINE"},
    }
    assert result["selected_window"]["title"] == "LINE Chat - Google Chrome"


def test_prefocus_computer_use_target_window_skips_when_no_target():
    import blocks.chat.send as send  # noqa: E402

    result = send._prefocus_computer_use_target_window(
        available_tools=[{"name": "browser_computer"}],
        base_context={"user_requested_computer_use": True},
        call_handler=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("call_handler should not run")),
    )

    assert result is None
