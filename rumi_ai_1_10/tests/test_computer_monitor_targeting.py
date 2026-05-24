from __future__ import annotations

import json
from pathlib import Path

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
    BrowserComputerController,
)


def _monitors() -> list[dict[str, object]]:
    return [
        {
            "id": "darwin:1",
            "monitor_id": "darwin:1",
            "display_id": 1,
            "index": 0,
            "name": "Built-in",
            "x": 0,
            "y": 0,
            "width": 1000,
            "height": 800,
            "bounds": {"x": 0, "y": 0, "width": 1000, "height": 800},
            "primary": True,
        },
        {
            "id": "darwin:2",
            "monitor_id": "darwin:2",
            "display_id": 2,
            "index": 1,
            "name": "Studio",
            "x": 1000,
            "y": 0,
            "width": 1200,
            "height": 900,
            "bounds": {"x": 1000, "y": 0, "width": 1200, "height": 900},
            "primary": False,
        },
    ]


def test_monitor_for_rect_uses_largest_overlap():
    match = BrowserComputerController._monitor_for_rect(
        {"x": 900, "y": 100, "width": 300, "height": 400},
        _monitors(),
    )

    assert match is not None
    assert match["monitor"]["monitor_id"] == "darwin:2"
    assert match["overlap_area"] == 80000


def test_select_monitor_updates_target_and_default_capture(tmp_path, monkeypatch):
    controller = BrowserComputerController(artifact_root=tmp_path / "artifacts")
    monkeypatch.setattr(controller, "_list_monitors", _monitors)

    selected = controller.run("select_monitor", {"monitor_id": "darwin:2"})

    assert selected["selected"] is True
    assert selected["target_monitor"]["monitor_id"] == "darwin:2"
    assert controller._capture_target({})["monitor_id"] == "darwin:2"
    assert controller._capture_target({"target": "desktop"})["monitor_id"] == "darwin:2"


def test_default_target_does_not_enumerate_monitors_without_selection(tmp_path, monkeypatch):
    controller = BrowserComputerController(artifact_root=tmp_path / "artifacts")

    def fail_list_monitors():
        raise AssertionError("monitor enumeration should be explicit or state-driven")

    monkeypatch.setattr(controller, "_list_monitors", fail_list_monitors)

    target = controller._computer_seat_target({"pid": 123})

    assert target["pid"] == 123
    assert target["monitor_id"] is None


def test_context_includes_selected_monitor(tmp_path, monkeypatch):
    controller = BrowserComputerController(artifact_root=tmp_path / "artifacts")
    monkeypatch.setattr(controller, "_list_monitors", _monitors)
    monkeypatch.setattr(controller, "_active_window", lambda: None)
    monkeypatch.setattr(controller, "_running_apps", lambda: [])

    controller.run("select_monitor", {"monitor_index": 1})
    context = controller.run("context", {"include_windows": False})

    assert context["selected_monitor"]["monitor_id"] == "darwin:2"
    assert [item["monitor_id"] for item in context["monitors"]] == ["darwin:1", "darwin:2"]


def test_list_windows_annotates_monitor(tmp_path, monkeypatch):
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = BrowserComputerController(artifact_root=tmp_path / "artifacts")
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(controller, "_list_monitors", _monitors)
    monkeypatch.setattr(
        controller,
        "_darwin_windows",
        lambda: [{"app": "Chrome", "title": "Gemini", "x": 1100, "y": 20, "width": 500, "height": 400, "active": True}],
    )

    windows = controller._list_windows()

    assert windows[0]["monitor_id"] == "darwin:2"
    assert windows[0]["monitor"]["bounds"] == {"x": 1000, "y": 0, "width": 1200, "height": 900}


def test_computer_seat_target_preserves_monitor_fields(tmp_path, monkeypatch):
    controller = BrowserComputerController(artifact_root=tmp_path / "artifacts")
    monkeypatch.setattr(controller, "_list_monitors", _monitors)
    controller.run("select_monitor", {"monitor_id": "darwin:2"})

    target = controller._computer_seat_target({"pid": 123, "window_id": 456})

    assert target["pid"] == 123
    assert target["window_id"] == 456
    assert target["monitor_id"] == "darwin:2"
    assert target["display_id"] == 2
    assert target["monitor_index"] == 1
    assert target["monitor_bounds"] == {"x": 1000, "y": 0, "width": 1200, "height": 900}


def test_computer_use_manifest_registers_monitor_actions():
    manifest = json.loads(
        (
            Path(__file__).resolve().parent.parent
            / "ecosystem"
            / "rumi_default_tools_pack"
            / "tools"
            / "computer_use"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    action_enum = manifest["config"]["schema"]["parameters"]["properties"]["action"]["enum"]
    properties = manifest["config"]["schema"]["parameters"]["properties"]

    assert "monitors" in action_enum
    assert "select_monitor" in action_enum
    assert "monitor_id" in properties
    assert "display_id" in properties
