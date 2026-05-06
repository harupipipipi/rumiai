from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


DEFAULTSPACK = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))


def test_macos_permissions_include_v2_preflight_fields(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        browser_computer.shutil,
        "which",
        lambda name: {
            "osascript": "/usr/bin/osascript",
            "screencapture": "/usr/sbin/screencapture",
            "cliclick": "/opt/homebrew/bin/cliclick",
        }.get(name),
    )
    monkeypatch.setattr(BrowserComputerController, "_python_module_preflight", staticmethod(lambda name: {"available": True, "status": "ok"}))
    monkeypatch.setattr(BrowserComputerController, "_darwin_screen_recording_preflight", lambda self, quartz: {"available": True, "allowed": True, "status": "ok"})
    monkeypatch.setattr(BrowserComputerController, "_darwin_accessibility_preflight", lambda self, quartz: {"available": True, "allowed": False, "status": "not_granted"})

    result = BrowserComputerController().run("computer.permissions")
    preflight = result["preflight"]

    assert set(preflight) == {
        "screen_recording",
        "accessibility",
        "automation_system_events",
        "screencapture",
        "osascript",
        "quartz",
        "cliclick",
    }
    assert preflight["screen_recording"]["allowed"] is True
    assert preflight["accessibility"]["status"] == "not_granted"
    assert preflight["cliclick"]["available"] is True


def test_computer_use_executor_forwards_target_coordinate_and_quality_fields():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "computer_use",
        {
            "action": "click",
            "target": "app",
            "app": "Vivaldi",
            "coordinate_space": "model_image",
            "x": 150,
            "y": 100,
            "quality": "high_detail",
            "model_image_path": "/tmp/screen-model.jpg",
        },
    )

    assert action == "computer.click"
    assert payload["target"] == "app"
    assert payload["coordinate_space"] == "model_image"
    assert payload["quality"] == "high_detail"
    assert payload["model_image_path"] == "/tmp/screen-model.jpg"


def test_computer_use_executor_accepts_natural_app_focus_alias():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "computer_use",
        {
            "action": "app.focus",
            "app": "Vivaldi",
        },
    )

    assert action == "computer.app.focus"
    assert payload["app"] == "Vivaldi"


def test_computer_use_executor_accepts_app_search_alias():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "computer_use",
        {
            "action": "app.find",
            "query": "Vivaldi",
        },
    )

    assert action == "computer.app.find"
    assert payload["query"] == "Vivaldi"


def test_browser_tool_operator_point_payload_is_forwarded():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "computer_use",
        {
            "action": "click",
            "point": [250, 750],
            "target": "app",
            "app": "Vivaldi",
        },
    )

    assert action == "computer.click"
    assert payload["point"] == [250, 750]


def test_windows_permissions_include_v2_preflight_fields(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(browser_computer.shutil, "which", lambda name: f"C:/Windows/{name}.exe" if name == "powershell" else None)
    monkeypatch.setattr(
        BrowserComputerController,
        "_windows_preflight_probe",
        lambda self: {
            "forms": True,
            "drawing": True,
            "desktop_session_active": True,
            "screen_locked": False,
            "dpi_scale": 1.25,
        },
    )

    preflight = BrowserComputerController().run("computer.permissions")["preflight"]

    assert set(preflight) == {
        "powershell",
        "pwsh",
        "forms",
        "drawing",
        "desktop_session_active",
        "screen_locked",
        "dpi_scale",
    }
    assert preflight["forms"]["allowed"] is True
    assert preflight["screen_locked"]["status"] == "unlocked"
    assert preflight["dpi_scale"] == 1.25


def test_computer_apps_list_filters_running_apps(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_apps",
        lambda self, limit: [
            {"name": "Codex", "app": "Codex", "pid": 1},
            {"name": "Vivaldi", "app": "Vivaldi", "pid": 2, "bundle_id": "com.vivaldi.Vivaldi"},
        ],
    )

    result = BrowserComputerController().run("computer.app.find", {"query": "vivaldi"})

    assert result.get("requires_approval") is not True
    assert result["found"] is True
    assert result["match"]["name"] == "Vivaldi"


def test_app_window_target_resolves_requested_app_window(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_windows",
        lambda self, limit: [
            {"app": "Codex", "title": "Rumi", "bounds": {"x": 0, "y": 0, "width": 500, "height": 400}},
            {"app": "Vivaldi", "title": "LINE Chat", "bounds": {"x": 50, "y": 60, "width": 700, "height": 500}},
        ],
    )
    monkeypatch.setattr(BrowserComputerController, "_darwin_active_window", lambda self: {"app": "Codex"})

    context = BrowserComputerController()._prepare_target_context(
        {"target": "app", "app": "Vivaldi", "focus": False},
        system="Darwin",
        focus=False,
    )

    assert context["scope"] == "app"
    assert context["window"]["app"] == "Vivaldi"
    assert context["bounds"] == {"x": 50, "y": 60, "width": 700, "height": 500}


def test_app_window_target_prefers_largest_app_window_over_toolbar(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_darwin_focus_app", lambda self, payload: None)
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_windows",
        lambda self, limit: [
            {"app": "Vivaldi", "title": "", "bounds": {"x": 0, "y": 0, "width": 1470, "height": 81}},
            {
                "app": "Vivaldi",
                "title": "LINE Chat - Vivaldi",
                "bounds": {"x": 0, "y": 37, "width": 1470, "height": 919},
            },
        ],
    )
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_active_window",
        lambda self: {"app": "Vivaldi", "title": "", "bounds": {"x": 0, "y": 0, "width": 1470, "height": 81}},
    )

    context = BrowserComputerController()._prepare_target_context(
        {"target": "app", "app": "Vivaldi"},
        system="Darwin",
        focus=True,
    )

    assert context["window"]["title"] == "LINE Chat - Vivaldi"
    assert context["bounds"] == {"x": 0, "y": 37, "width": 1470, "height": 919}


def test_screenshot_result_includes_display_and_dpi_metadata(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController

    screenshot = tmp_path / "screen.png"
    model_image = tmp_path / "screen-model.png"
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
    screenshot.write_bytes(png_header + b"\x00\x00\x05\xa0\x00\x00\x03\x84")
    model_image.write_bytes(png_header + b"\x00\x00\x02\x80\x00\x00\x01\x90")
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: None))
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_displays",
        lambda self: [
            {
                "id": "1",
                "primary": True,
                "bounds": {"x": 0, "y": 0, "width": 720, "height": 450},
                "pixel_size": {"width": 1440, "height": 900},
                "dpi_scale": 2.0,
            }
        ],
    )

    result = BrowserComputerController()._screenshot_result(screenshot, model_image, "Darwin")

    assert result["display_metadata"]["primary"]["dpi_scale"] == 2.0
    assert result["display_metadata"]["captured_pixel_size"] == {"width": 1440, "height": 900}
    assert result["display_metadata"]["screenshot_to_display_scale"] == {"x": 2.0, "y": 2.0}


def test_read_only_screenshot_does_not_block_on_approval(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_prepare_target_context", lambda self, payload, system, focus: {"scope": "desktop"})
    monkeypatch.setattr(BrowserComputerController, "_target_capture_bounds", lambda self, target_context: None)
    monkeypatch.setattr(
        browser_computer.subprocess,
        "run",
        lambda command, check: (tmp_path / "screenshot-1.png").write_bytes(b"\x89PNG\r\n\x1a\n"),
    )
    monkeypatch.setattr(
        BrowserComputerController,
        "_screenshot_result",
        lambda self, path, model_image_path, system, **kwargs: {"action": "computer.screenshot", "path": str(path), "requires_approval": False},
    )

    result = BrowserComputerController(artifact_root=tmp_path).run("computer.screenshot")

    assert result["action"] == "computer.screenshot"
    assert result["requires_approval"] is False


def test_zoom_crops_latest_screenshot_and_returns_coordinate_metadata(tmp_path):
    from domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    screenshot = tmp_path / "screenshot-100.png"
    rows = []
    for y in range(6):
        row = bytearray()
        for x in range(8):
            row.extend([x, y, 200, 255])
        rows.append(row)
    controller._write_png_pixels(
        screenshot,
        {"width": 8, "height": 6, "channels": 4, "color_type": 6, "rows": rows},
    )

    result = controller.run("computer.zoom", {"latest": True, "x": 4, "y": 3, "width": 4, "height": 2, "scale": 2})

    assert result["action"] == "computer.zoom"
    assert result["source_path"] == str(screenshot)
    assert result["crop_bounds"] == {"x": 2, "y": 2, "width": 4, "height": 2, "right": 6, "bottom": 4}
    assert result["center"] == {"x": 4, "y": 3, "coordinate_space": "source_image"}
    assert result["scale"] == 2.0
    assert result["image_size"] == {"width": 8, "height": 4}
    assert result["source_image_size"] == {"width": 8, "height": 6}
    assert result["data_url"].startswith("data:image/png;base64,")
    assert result["visual_data_url"].startswith("data:image/png;base64,")
    assert result["annotation"]["x"] == 4
    assert result["annotation"]["y"] == 2
    assert result["annotation"]["coordinate_space"] == "zoom_image"
    assert result["annotation"]["source"] == {"x": 4, "y": 3, "coordinate_space": "source_image"}
    assert Path(result["path"]).is_file()


def test_zoom_converts_model_image_coordinates_to_source_screenshot(tmp_path):
    from domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    screenshot = tmp_path / "screenshot-100.png"
    rows = []
    for y in range(8):
        row = bytearray()
        for x in range(8):
            row.extend([x, y, 200, 255])
        rows.append(row)
    controller._write_png_pixels(
        screenshot,
        {"width": 8, "height": 8, "channels": 4, "color_type": 6, "rows": rows},
    )
    (tmp_path / "screenshot-100.json").write_text(
        json.dumps(
            {
                "path": str(screenshot),
                "metadata_path": str(tmp_path / "screenshot-100.json"),
                "image_size": {"width": 8, "height": 8},
                "model_image_size": {"width": 4, "height": 4},
            }
        ),
        encoding="utf-8",
    )

    result = controller.run(
        "computer.zoom",
        {"latest": True, "coordinate_space": "model_image", "x": 2, "y": 2, "width": 4, "height": 4},
    )

    assert result["center"] == {"x": 4, "y": 4, "coordinate_space": "source_image"}
    assert result["source_point"] == {"type": "point", "x": 2, "y": 2, "coordinate_space": "model_image", "label": "zoom-source"}


def test_computer_click_and_move_results_include_point_annotations(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0))
    monkeypatch.setattr(browser_computer.shutil, "which", lambda name: "/opt/homebrew/bin/cliclick" if name == "cliclick" else None)

    click = BrowserComputerController().run("computer.click", {"x": 11, "y": 22}, yolo_mode=True)
    move = BrowserComputerController().run("computer.move", {"x": 33, "y": 44, "dry_run": True})

    assert click["annotation"] == {"type": "point", "x": 11, "y": 22, "coordinate_space": "action", "label": "click"}
    assert click["overlay_points"] == [click["annotation"]]
    assert move["annotation"] == {"type": "point", "x": 33, "y": 44, "coordinate_space": "action", "label": "move"}
    assert move["overlay_points"] == [move["annotation"]]


def test_computer_move_updates_virtual_cursor_without_moving_real_mouse(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    calls = []
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "computer.move",
        {"x": 41, "y": 52},
        yolo_mode=True,
    )
    state = json.loads((tmp_path / "virtual_cursor.json").read_text(encoding="utf-8"))

    assert result["executed"] is True
    assert state["type"] == "virtual_cursor"
    assert state["target"] == {"x": 41, "y": 52}
    assert calls == []


def test_screenshot_burns_virtual_cursor_into_visual(tmp_path):
    from domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    screenshot = tmp_path / "screenshot-virtual.png"
    rows = [bytearray([255, 255, 255, 255] * 30) for _ in range(30)]
    controller._write_png_pixels(
        screenshot,
        {"width": 30, "height": 30, "channels": 4, "color_type": 6, "rows": rows},
    )
    controller._write_virtual_cursor(
        {
            "type": "virtual_cursor",
            "points": [
                {"type": "point", "x": 4, "y": 5, "coordinate_space": "screenshot_image", "label": "move"}
            ],
        }
    )

    result = {
        "path": str(screenshot),
        "image_size": {"width": 30, "height": 30},
        "action_coordinate_system": {"width": 30, "height": 30},
    }
    controller._attach_screenshot_overlays(result)

    assert Path(result["click_history_visual_path"]).is_file()
    assert result["virtual_cursor_overlay_point"]["label"] == "ai-cursor"
    assert result["virtual_cursor_overlay_point"]["x"] == 4


def test_windows_hotkey_translation_executes_sendkeys(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    scripts = []
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(BrowserComputerController, "_run_powershell", staticmethod(lambda script: scripts.append(script)))

    result = BrowserComputerController().run("computer.hotkey", {"combo": "ctrl+shift+escape"}, yolo_mode=True)

    assert result["executed"] is True
    assert result["hotkey"] == {"modifiers": ["ctrl", "shift"], "key": "esc", "combo": "ctrl+shift+esc"}
    assert "[System.Windows.Forms.SendKeys]::SendWait('^+{ESC}')" in scripts[0]


def test_high_risk_clipboard_write_requires_server_approved_token(tmp_path, monkeypatch):
    from domain.approval.store import ApprovalStore
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="")

    controller = BrowserComputerController()
    controller._approval_path = tmp_path / "approvals.json"
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    required = controller.run("computer.clipboard.write", {"text": "hello"})
    still_required = controller.run(
        "computer.clipboard.write",
        {"text": "hello", "approval_id": required["approval_id"], "approval_token": "client-token"},
    )
    approved = ApprovalStore(controller._approval_path).approve_once(required["approval_id"])
    executed = controller.run(
        "computer.clipboard.write",
        {
            "text": "hello",
            "approval_id": required["approval_id"],
            "approval_token": approved["approval_token"],
        },
    )

    assert required["requires_approval"] is True
    assert required["risk_level"] == "high"
    assert "approval_token" not in required
    assert still_required["requires_approval"] is True
    assert executed["executed"] is True
    assert calls[-1][0] == ["pbcopy"]
    assert calls[-1][1]["input"] == "hello"


def test_computer_displays_list_uses_windows_probe(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    payload = [
        {
            "id": "\\\\.\\DISPLAY1",
            "primary": True,
            "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "dpi_scale": 1.5,
        }
    ]
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(BrowserComputerController, "_run_powershell_json", lambda self, script: json.loads(json.dumps(payload)))

    result = BrowserComputerController().run("computer.displays.list")

    assert result["count"] == 1
    assert result["displays"][0]["primary"] is True
    assert result["displays"][0]["dpi_scale"] == 1.5


def test_screenshot_can_target_active_window_region(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    controller = BrowserComputerController(artifact_root=tmp_path)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "screencapture":
            controller._write_png_pixels(
                Path(command[-1]),
                {"width": 300, "height": 200, "channels": 4, "color_type": 6, "rows": [bytearray([0, 0, 0, 255] * 300) for _ in range(200)]},
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)
    monkeypatch.setattr(BrowserComputerController, "_model_screenshot_copy", lambda self, path: path)
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: None))
    monkeypatch.setattr(BrowserComputerController, "_darwin_displays", lambda self: [])
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_active_window",
        lambda self: {
            "id": "frontmost",
            "app": "Vivaldi",
            "title": "LINE",
            "bounds": {"x": 10, "y": 20, "width": 300, "height": 200},
        },
    )

    result = controller.run("computer.screenshot", {"target": "active_window"}, yolo_mode=True)

    assert commands[0][:4] == ["screencapture", "-x", "-R", "10,20,300,200"]
    assert result["target"]["scope"] == "active_window"
    assert result["target"]["origin"] == {"x": 10, "y": 20}
    assert result["screenshot_origin"] == {"x": 10, "y": 20}
    assert result["coordinate_system"]["x_range"] == [0, 299]


def test_retina_window_screenshot_exposes_target_local_scales(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController

    screenshot = tmp_path / "screen.png"
    model_image = tmp_path / "screen-model.png"
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
    screenshot.write_bytes(png_header + b"\x00\x00\x02\x58\x00\x00\x01\x90")
    model_image.write_bytes(png_header + b"\x00\x00\x01,\x00\x00\x00\xc8")
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: None))
    monkeypatch.setattr(BrowserComputerController, "_darwin_displays", lambda self: [])

    result = BrowserComputerController()._screenshot_result(
        screenshot,
        model_image,
        "Darwin",
        target_context={
            "scope": "app",
            "bounds": {"x": 100, "y": 200, "width": 300, "height": 200},
            "origin": {"x": 100, "y": 200},
            "coordinate_space": "target_window",
        },
    )

    assert result["target_action_size"] == {"width": 300, "height": 200}
    assert result["screenshot_to_target_scale"] == {"x": 0.5, "y": 0.5}
    assert result["model_to_target_scale"] == {"x": 1.0, "y": 1.0}
    assert result["target_to_action_offset"] == {"x": 100, "y": 200}


def test_app_window_click_converts_screenshot_coordinates_to_desktop(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    clicked = {}
    metadata = {
        "path": str(tmp_path / "screenshot-1.png"),
        "metadata_path": str(tmp_path / "screenshot-1.json"),
        "image_size": {"width": 600, "height": 400},
        "model_image_size": {"width": 300, "height": 200},
        "target": {
            "scope": "app",
            "bounds": {"x": 100, "y": 200, "width": 300, "height": 200},
            "origin": {"x": 100, "y": 200},
        },
    }
    (tmp_path / "screenshot-1.json").write_text(json.dumps(metadata), encoding="utf-8")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_darwin_focus_app", lambda self, payload: None)
    monkeypatch.setattr(BrowserComputerController, "_darwin_windows", lambda self, limit: [])
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_active_window",
        lambda self: {
            "id": "frontmost",
            "app": "Vivaldi",
            "title": "LINE",
            "bounds": {"x": 100, "y": 200, "width": 300, "height": 200},
        },
    )
    monkeypatch.setattr(BrowserComputerController, "_darwin_click", lambda self, payload: clicked.update(payload))

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "computer.click",
        {"target": "app", "app": "Vivaldi", "coordinate_space": "screenshot_image", "x": 300, "y": 200},
        yolo_mode=True,
    )

    assert clicked["x"] == 250
    assert clicked["y"] == 300
    assert result["target"] == {"x": 250, "y": 300}
    assert result["local_target"] == {"x": 150, "y": 100}
    assert result["coordinate_transform"]["screenshot_point"]["x"] == 300
    assert result["coordinate_transform"]["target_window_point"] == {
        "type": "point",
        "x": 150,
        "y": 100,
        "coordinate_space": "target_window",
        "label": "target-window",
    }


def test_app_window_click_converts_model_image_coordinates_to_desktop(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    clicked = {}
    metadata = {
        "path": str(tmp_path / "screenshot-1.png"),
        "metadata_path": str(tmp_path / "screenshot-1.json"),
        "image_size": {"width": 600, "height": 400},
        "model_image_size": {"width": 300, "height": 200},
        "target": {
            "scope": "app",
            "bounds": {"x": 100, "y": 200, "width": 300, "height": 200},
            "origin": {"x": 100, "y": 200},
        },
    }
    (tmp_path / "screenshot-1.json").write_text(json.dumps(metadata), encoding="utf-8")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_darwin_focus_app", lambda self, payload: None)
    monkeypatch.setattr(BrowserComputerController, "_darwin_windows", lambda self, limit: [])
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_active_window",
        lambda self: {
            "id": "frontmost",
            "app": "Vivaldi",
            "title": "LINE",
            "bounds": {"x": 100, "y": 200, "width": 300, "height": 200},
        },
    )
    monkeypatch.setattr(BrowserComputerController, "_darwin_click", lambda self, payload: clicked.update(payload))

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "computer.click",
        {"target": "app", "app": "Vivaldi", "coordinate_space": "model_image", "x": 150, "y": 100},
        yolo_mode=True,
    )

    assert clicked["x"] == 250
    assert clicked["y"] == 300
    assert result["coordinate_transform"]["input"]["coordinate_space"] == "model_image"
    assert result["coordinate_transform"]["screenshot_point"]["x"] == 300
    assert result["coordinate_transform"]["screenshot_point"]["y"] == 200


def test_click_infers_screenshot_coordinates_when_point_exceeds_action_space(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    clicked = {}
    metadata = {
        "path": str(tmp_path / "screenshot-1.png"),
        "metadata_path": str(tmp_path / "screenshot-1.json"),
        "image_size": {"width": 600, "height": 400},
        "action_coordinate_system": {"width": 300, "height": 200},
    }
    (tmp_path / "screenshot-1.json").write_text(json.dumps(metadata), encoding="utf-8")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_darwin_click", lambda self, payload: clicked.update(payload))

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "computer.click",
        {"x": 300, "y": 300},
        yolo_mode=True,
    )

    assert clicked["x"] == 150
    assert clicked["y"] == 150
    assert result["target"] == {"x": 150, "y": 150}
    assert result["coordinate_transform"]["input"] == {
        "type": "point",
        "x": 300,
        "y": 300,
        "coordinate_space": "screenshot_image",
        "label": "source",
    }


def test_click_accepts_browser_operator_normalized_yx_point(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    clicked = {}
    metadata = {
        "path": str(tmp_path / "screenshot-1.png"),
        "metadata_path": str(tmp_path / "screenshot-1.json"),
        "image_size": {"width": 600, "height": 400},
        "action_coordinate_system": {"width": 300, "height": 200},
    }
    (tmp_path / "screenshot-1.json").write_text(json.dumps(metadata), encoding="utf-8")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_darwin_click", lambda self, payload: clicked.update(payload))

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "computer.click",
        {"point": [250, 750]},
        yolo_mode=True,
    )

    assert clicked["x"] == 225
    assert clicked["y"] == 50
    assert result["coordinate_transform"]["normalized_point"] == {
        "type": "point",
        "x": 750,
        "y": 250,
        "coordinate_space": "normalized_1000",
        "label": "normalized",
    }


def test_screenshot_burns_recent_click_history_into_visual(tmp_path):
    from domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    screenshot = tmp_path / "screenshot-200.png"
    rows = [bytearray([255, 255, 255, 255] * 20) for _ in range(20)]
    controller._write_png_pixels(
        screenshot,
        {"width": 20, "height": 20, "channels": 4, "color_type": 6, "rows": rows},
    )
    controller._write_click_history(
        [
            {
                "action": "computer.click",
                "points": [
                    {"type": "point", "x": 10, "y": 11, "coordinate_space": "screenshot_image", "label": "click"}
                ],
            }
        ]
    )

    result = {
        "path": str(screenshot),
        "image_size": {"width": 20, "height": 20},
        "action_coordinate_system": {"width": 20, "height": 20},
    }
    controller._attach_screenshot_overlays(result)

    assert Path(result["click_history_visual_path"]).is_file()
    assert result["click_history_overlay_points"][0]["x"] == 10
    assert result["click_history_visual_data_url"].startswith("data:image/png;base64,")


def test_app_window_click_offsets_local_coordinates(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    clicked = {}

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_darwin_focus_app", lambda self, payload: None)
    monkeypatch.setattr(BrowserComputerController, "_darwin_windows", lambda self, limit: [])
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_active_window",
        lambda self: {
            "id": "frontmost",
            "app": "Vivaldi",
            "title": "LINE",
            "bounds": {"x": 100, "y": 200, "width": 500, "height": 400},
        },
    )
    monkeypatch.setattr(BrowserComputerController, "_darwin_click", lambda self, payload: clicked.update(payload))

    result = BrowserComputerController().run(
        "computer.click",
        {"target": "app", "app": "Vivaldi", "x": 12, "y": 34},
        yolo_mode=True,
    )

    assert clicked["x"] == 112
    assert clicked["y"] == 234
    assert result["target"] == {"x": 112, "y": 234}
    assert result["local_target"] == {"x": 12, "y": 34}
    assert result["target_context"]["scope"] == "app"


def test_desktop_click_keeps_absolute_coordinates(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    clicked = {}

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_darwin_click", lambda self, payload: clicked.update(payload))

    result = BrowserComputerController().run(
        "computer.click",
        {"target": "full_desktop", "x": 12, "y": 34},
        yolo_mode=True,
    )

    assert clicked["x"] == 12
    assert clicked["y"] == 34
    assert "local_target" not in result
    assert result["target_context"]["scope"] == "full_desktop"


def test_darwin_type_uses_clipboard_paste_for_text(monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        if command == ["pbpaste"]:
            return subprocess.CompletedProcess(command, 0, stdout="old")
        return subprocess.CompletedProcess(command, 0, stdout="")

    posted = []
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)
    monkeypatch.setattr(BrowserComputerController, "_darwin_post_key", lambda self, key, modifiers=None, pid=None: posted.append((key, modifiers, pid)))

    result = BrowserComputerController().run("computer.type", {"text": "Gemma 4 testです"}, yolo_mode=True)

    assert result["executed"] is True
    assert [command for command, _ in commands] == [["pbpaste"], ["pbcopy"], ["pbcopy"]]
    assert commands[1][1]["input"] == "Gemma 4 testです"
    assert commands[2][1]["input"] == "old"
    assert posted == [("v", ["cmd"], None)]


def test_darwin_type_prefers_ax_text_at_virtual_cursor_for_target_app(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    ax_calls = []
    posted = []
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        BrowserComputerController,
        "_prepare_target_context",
        lambda self, payload, system, focus: {
            "scope": "app",
            "window": {"pid": 123, "app": "Vivaldi", "bounds": {"x": 0, "y": 0, "width": 500, "height": 400}},
            "bounds": {"x": 0, "y": 0, "width": 500, "height": 400},
            "origin": {"x": 0, "y": 0},
        },
    )
    monkeypatch.setattr(
        BrowserComputerController,
        "_darwin_ax_set_text_at_point",
        staticmethod(lambda x, y, pid, text: ax_calls.append((x, y, pid, text)) or True),
    )
    monkeypatch.setattr(BrowserComputerController, "_darwin_post_key", lambda self, key, modifiers=None, pid=None: posted.append((key, modifiers, pid)))

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._write_virtual_cursor({"target": {"x": 40, "y": 50}})

    result = controller.run(
        "computer.type",
        {"target": "app", "app": "Vivaldi", "text": "hello\n"},
        yolo_mode=True,
    )

    assert result["executed"] is True
    assert ax_calls == [(40, 50, 123, "hello")]
    assert posted == [("return", None, 123)]


def test_target_app_without_window_uses_pid_instead_of_active_window(tmp_path, monkeypatch):
    from domain.tool.browser_computer import BrowserComputerController
    import domain.tool.browser_computer as browser_computer

    typed = []
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    controller = BrowserComputerController(artifact_root=tmp_path)
    monkeypatch.setattr(controller, "_darwin_windows", lambda limit: [])
    monkeypatch.setattr(
        controller,
        "_darwin_active_window",
        lambda: {"app": "Codex", "pid": 1, "bounds": {"x": 1, "y": 2, "width": 3, "height": 4}},
    )
    monkeypatch.setattr(
        controller,
        "_darwin_apps",
        lambda limit: [{"app": "Vivaldi", "name": "Vivaldi", "pid": 222, "bundle_id": "com.vivaldi.Vivaldi"}],
    )
    monkeypatch.setattr(controller, "_darwin_ax_set_text_at_point", lambda x, y, pid, text: typed.append((pid, text)) or True)
    controller._write_virtual_cursor({"target": {"x": 40, "y": 50}})

    result = controller.run("computer.type", {"app": "Vivaldi", "target": "app", "text": "hello"}, yolo_mode=True)

    assert result["executed"] is True
    assert result["target_context"]["app"] == "Vivaldi"
    assert result["target_context"]["pid"] == 222
    assert typed == [(222, "hello")]
