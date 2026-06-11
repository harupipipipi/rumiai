from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_show_app_stores_active_window_for_selected_app(monkeypatch, tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    active_window = {
        "app": "Google Chrome",
        "title": "Gemini",
        "pid": 123,
        "window_id": 456,
        "bounds": {"x": 10, "y": 20, "width": 800, "height": 600},
    }

    monkeypatch.setattr(
        controller,
        "_select_app",
        lambda payload: {
            "action": "computer.select_app",
            "selected": True,
            "target_app": {"name": "Google Chrome", "app": "Google Chrome", "running": True},
        },
    )
    monkeypatch.setattr(controller, "_active_window_for_app", lambda app_name: active_window)
    monkeypatch.setattr(controller, "_active_window", lambda: active_window)
    monkeypatch.setattr(controller, "_matching_window", lambda payload: None)
    monkeypatch.setattr("ecosystem.rumi_default_tools_pack.domain.tool.browser_computer.time.sleep", lambda seconds: None)

    result = controller.run("computer.show_app", {"app": "Google Chrome"})

    assert result["shown"] is True
    assert result["target_window"] == active_window
    assert controller._computer_state()["target_window"] == active_window


def test_darwin_window_listing_times_out_automation_fallback(monkeypatch, tmp_path):
    import subprocess

    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    monkeypatch.setattr(controller, "_darwin_windows_quartz", lambda: [])
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))

    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    assert controller._darwin_windows() == []
    assert seen["command"][:2] == ["osascript", "-e"]
    assert seen["timeout"] == browser_computer._DARWIN_AUTOMATION_TIMEOUT_SECONDS
