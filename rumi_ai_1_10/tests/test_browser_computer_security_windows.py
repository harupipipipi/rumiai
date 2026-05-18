from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ecosystem" / "defaultspack"))


def _controller(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._approval_path = tmp_path / "shared" / "browser_computer_approvals.json"
    return controller


def test_screenshot_requires_approval_before_capture_reuse_or_crop(tmp_path, monkeypatch):
    controller = _controller(tmp_path)

    monkeypatch.setattr(
        controller,
        "_capture_or_reuse_screenshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("capture/reuse must wait for approval")),
    )
    monkeypatch.setattr(
        controller,
        "_apply_screenshot_crop",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("crop must wait for approval")),
    )

    result = controller.run(
        "computer.screenshot",
        {"source": "latest", "crop": {"x": 1, "y": 2, "width": 3, "height": 4}},
    )

    assert result["requires_approval"] is True
    assert result["action"] == "computer.screenshot"
    assert result["payload"]["source"] == "latest"
    assert result["payload"]["crop"]["width"] == 3


def test_yolo_string_false_does_not_bypass_screenshot_approval(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    monkeypatch.setattr(
        controller,
        "_capture_or_reuse_screenshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("string false is not yolo")),
    )

    result = controller.run("computer.screenshot", {}, yolo_mode="false")

    assert result["requires_approval"] is True


def test_user_requested_computer_use_does_not_bypass_local_executor_approval(tmp_path, monkeypatch):
    from domain.tool import executor as executor_module

    ToolExecutor = executor_module.ToolExecutor
    monkeypatch.setattr(executor_module, "policy_from_context", lambda context: context.get("profile_policy", {}))

    monkeypatch.setattr(
        "ecosystem.rumi_default_tools_pack.domain.tool.browser_computer.BrowserComputerController._capture_action_result_screenshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("click must not execute before approval")),
    )
    monkeypatch.setattr(
        "ecosystem.rumi_default_tools_pack.domain.tool.browser_computer.BrowserComputerController._window_at_point",
        lambda self, x, y: None,
    )

    executor = ToolExecutor.__new__(ToolExecutor)
    result = executor._execute_local(
        "browser_computer",
        {"action": "computer.click", "payload": {"x": 10, "y": 20, "coordinate_space": "screen"}},
        {
            "user_requested_computer_use": True,
            "conversation_workspace_dir": str(tmp_path),
            "profile_policy": {"yolo_mode": "false"},
        },
    )

    assert result["is_error"] is False
    assert result["widget"]["requires_approval"] is True
    assert result["widget"]["payload"]["virtual_only"] is True
    assert result["widget"]["payload"]["resolved_coordinates"] == {"x": 10, "y": 20}


def test_open_url_approval_payload_includes_target_app(tmp_path):
    controller = _controller(tmp_path)

    result = controller.run(
        "browser.open_url",
        {"url": "https://example.test", "app": "Microsoft Edge", "persistent": False},
    )

    assert result["requires_approval"] is True
    assert result["payload"]["target_app"] == "Microsoft Edge"


def test_open_url_function_context_target_app_reaches_approval_payload(tmp_path):
    from ecosystem.rumi_default_tools_pack.functions.browser_computer import main

    result = main.run(
        {"conversation_workspace_dir": str(tmp_path), "computer_use_target_app": "Microsoft Edge"},
        {"action": "browser.open_url", "payload": {"url": "https://example.test", "persistent": False}},
    )

    assert result["widget"]["requires_approval"] is True
    assert result["widget"]["payload"]["target_app"] == "Microsoft Edge"


def test_pointer_actions_default_virtual_and_include_resolved_coordinates(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    monkeypatch.setattr(controller, "_window_at_point", lambda x, y: None)

    click = controller.run("computer.click", {"x": 10, "y": 20})
    drag = controller.run("computer.drag", {"x1": 1, "y1": 2, "x2": 30, "y2": 40})

    assert click["requires_approval"] is True
    assert click["payload"]["virtual_only"] is True
    assert click["payload"]["resolved_coordinates"] == {"x": 10, "y": 20}
    assert drag["requires_approval"] is True
    assert drag["payload"]["virtual_only"] is True
    assert drag["payload"]["resolved_coordinates"] == {
        "from": {"x": 1, "y": 2},
        "to": {"x": 30, "y": 40},
    }


def test_default_click_uses_virtual_cursor_until_physical_true(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    monkeypatch.setattr(controller, "_capture_action_result_screenshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(controller, "_window_at_point", lambda x, y: None)
    monkeypatch.setattr(
        controller,
        "_windows_desktop_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("default click should stay virtual")),
    )

    result = controller.run("computer.click", {"x": 10, "y": 20}, yolo_mode=True)

    assert result["executed"] is True
    assert result["virtual_cursor"] is True


def test_windows_open_url_can_target_specific_browser(monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    calls = []

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(browser_computer.shutil, "which", lambda name: r"C:\Browsers\msedge.exe" if name == "Microsoft Edge" else None)
    monkeypatch.setattr(
        browser_computer.subprocess,
        "Popen",
        lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0),
    )

    assert BrowserComputerController._open_url_foreground("https://example.test", app_name="Microsoft Edge") is True
    assert calls[0][0].lower().endswith("msedge.exe")
    assert calls[0][1] == "https://example.test"


def test_windows_virtual_screen_coordinates_are_reported_for_desktop_capture(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = _controller(tmp_path)
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        controller,
        "_windows_screenshot",
        lambda path, target=None: {
            "x": -1920,
            "y": 0,
            "width": 3840,
            "height": 1080,
            "screen": "virtual_screen",
            "unit": "display_coordinate",
        },
    )

    result = controller._capture_screenshot(tmp_path / "shot.png", {"target": "desktop"})

    assert result["action_coordinate_system"]["screen"] == "virtual_screen"
    assert result["action_coordinate_system"]["x_range"] == [-1920, 1919]


def test_windows_sendkeys_escapes_literals_and_supports_modifiers():
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    assert BrowserComputerController._windows_sendkeys_escape_text("a+b{c}\n") == "a{+}b{{}c{}}{ENTER}"
    assert BrowserComputerController._windows_send_key("p", ["ctrl", "shift"]) == "^+p"
    assert BrowserComputerController._windows_send_key("ctrl+escape") == "^{ESC}"
    assert BrowserComputerController._windows_send_key("pagedown") == "{PGDN}"
    assert BrowserComputerController._windows_send_key("pageup") == "{PGUP}"
    assert BrowserComputerController._windows_send_key("back") == "{BACKSPACE}"
    assert BrowserComputerController._windows_send_key("back", ["alt"]) == "%{LEFT}"
    assert BrowserComputerController._windows_send_key("alt+back") == "%{LEFT}"


def test_windows_drag_steps_and_scrolls_at_point(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    scripts = []
    monkeypatch.setattr(controller, "_run_powershell", scripts.append)
    monkeypatch.setattr(controller, "_resolve_action_point", lambda payload, **kwargs: ({"x": 45, "y": 55}, None))

    controller._windows_desktop_action("computer.drag", {"x1": 1, "y1": 2, "x2": 30, "y2": 40})
    controller._windows_desktop_action("computer.scroll", {"x": 10, "y": 20, "amount": -2})

    assert "$steps = 12" in scripts[0]
    assert "Start-Sleep -Milliseconds 15" in scripts[0]
    assert "New-Object System.Drawing.Point(45, 55)" in scripts[1]
    assert "mouse_event(0x0800, 0, 0, -240" in scripts[1]


def test_windows_focus_window_uses_foreground_api(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = _controller(tmp_path)
    scripts = []
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(controller, "_run_powershell", scripts.append)

    controller._focus_window({"app": "chrome", "title": "LINE Chat - Google Chrome", "window_id": 1234})

    assert scripts
    assert "ShowWindowAsync($hwnd, 9)" in scripts[0]
    assert "BringWindowToTop($hwnd)" in scripts[0]
    assert "SetForegroundWindow($hwnd)" in scripts[0]
    assert "AppActivate($title)" in scripts[0]
    assert "$hwnd = [IntPtr]1234" in scripts[0]


def test_windows_type_uses_clipboard_paste_for_non_ascii_text(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    scripts = []

    monkeypatch.setattr(controller, "_run_powershell", scripts.append)

    controller._windows_desktop_action("computer.type", {"text": "こんにちは"})

    assert scripts
    assert "Set-Clipboard -Value $rumiPasteText" in scripts[0]
    assert "[System.Windows.Forms.SendKeys]::SendWait('^v')" in scripts[0]


def test_physical_click_refocuses_before_final_coordinate_resolution(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = _controller(tmp_path)
    steps = []
    desktop_actions = []
    focused = {"value": False}

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")

    def fake_resolve_action_point(payload, **kwargs):
        remember_cursor = kwargs.get("remember_cursor", False)
        steps.append(("resolve_click", remember_cursor, focused["value"]))
        if remember_cursor and focused["value"]:
            return ({"x": 110, "y": 220, "app": "Google Chrome", "title": "LINE Chat"}, None)
        return ({"x": 10, "y": 20, "app": "Google Chrome", "title": "LINE Chat"}, None)

    def fake_focus_action_target(payload):
        steps.append(("focus_click", payload["x"], payload["y"]))
        focused["value"] = True
        return True

    monkeypatch.setattr(controller, "_resolve_action_point", fake_resolve_action_point)
    monkeypatch.setattr(controller, "_focus_action_target", fake_focus_action_target)
    monkeypatch.setattr(controller, "_foreground_action_focus_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, "_try_computer_seat_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, "_windows_desktop_action", lambda action, payload: desktop_actions.append((action, payload)))
    monkeypatch.setattr(controller, "_capture_action_result_screenshot", lambda *args, **kwargs: {})

    result = controller.run(
        "computer.click",
        {"physical": True, "app": "Google Chrome", "title": "LINE Chat"},
        yolo_mode=True,
    )

    assert result["executed"] is True
    assert steps[:3] == [
        ("resolve_click", False, False),
        ("focus_click", 10, 20),
        ("resolve_click", True, True),
    ]
    assert desktop_actions == [
        (
            "computer.click",
            {"x": 110, "y": 220, "app": "Google Chrome", "title": "LINE Chat"},
        )
    ]


def test_physical_drag_refocuses_before_final_coordinate_resolution(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = _controller(tmp_path)
    steps = []
    desktop_actions = []
    focused = {"value": False}

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")

    def fake_resolve_drag_points(payload, remember_cursor=False):
        steps.append(("resolve_drag", remember_cursor, focused["value"]))
        if remember_cursor and focused["value"]:
            return (
                {"x1": 101, "y1": 202, "x2": 303, "y2": 404, "app": "Google Chrome", "title": "LINE Chat"},
                None,
                None,
            )
        return (
            {"x1": 1, "y1": 2, "x2": 30, "y2": 40, "app": "Google Chrome", "title": "LINE Chat"},
            None,
            None,
        )

    def fake_focus_action_target(payload):
        steps.append(("focus_drag", payload["x1"], payload["y1"], payload["x2"], payload["y2"]))
        focused["value"] = True
        return True

    monkeypatch.setattr(controller, "_resolve_drag_points", fake_resolve_drag_points)
    monkeypatch.setattr(controller, "_focus_action_target", fake_focus_action_target)
    monkeypatch.setattr(controller, "_foreground_action_focus_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, "_try_computer_seat_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, "_windows_desktop_action", lambda action, payload: desktop_actions.append((action, payload)))
    monkeypatch.setattr(controller, "_capture_action_result_screenshot", lambda *args, **kwargs: {})

    result = controller.run(
        "computer.drag",
        {"physical": True, "app": "Google Chrome", "title": "LINE Chat"},
        yolo_mode=True,
    )

    assert result["executed"] is True
    assert steps[:3] == [
        ("resolve_drag", False, False),
        ("focus_drag", 1, 2, 30, 40),
        ("resolve_drag", True, True),
    ]
    assert desktop_actions == [
        (
            "computer.drag",
            {"x1": 101, "y1": 202, "x2": 303, "y2": 404, "app": "Google Chrome", "title": "LINE Chat"},
        )
    ]


def test_foreground_type_refuses_when_selected_window_is_not_active(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = _controller(tmp_path)
    target_window = {
        "app": "chrome",
        "title": "LINE Chat - Google Chrome",
        "x": 10,
        "y": 20,
        "width": 900,
        "height": 700,
        "window_id": 200,
    }
    active_window = {
        "app": "Codex",
        "title": "Codex",
        "x": 0,
        "y": 0,
        "width": 900,
        "height": 700,
        "window_id": 100,
    }
    focus_calls = []

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(controller, "_matching_window", lambda payload: target_window)
    monkeypatch.setattr(controller, "_active_window", lambda: active_window)
    monkeypatch.setattr(controller, "_focus_window", lambda window: focus_calls.append(window))
    monkeypatch.setattr(controller, "_try_computer_seat_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        controller,
        "_windows_desktop_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("type must not hit the active Codex window")),
    )

    result = controller.run(
        "computer.type",
        {"text": "hello", "app": "Google Chrome", "title": "LINE Chat"},
        yolo_mode=True,
    )

    assert result["is_error"] is True
    assert result["executed"] is False
    assert result["recovery"]["kind"] == "focus_required"
    assert result["active_window"]["app"] == "Codex"
    assert result["selected_window"]["title"] == "LINE Chat - Google Chrome"
    assert focus_calls


def test_foreground_type_executes_when_selected_window_is_active(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = _controller(tmp_path)
    target_window = {
        "app": "chrome",
        "title": "LINE Chat - Google Chrome",
        "x": 10,
        "y": 20,
        "width": 900,
        "height": 700,
        "window_id": 200,
    }
    desktop_actions = []

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(controller, "_matching_window", lambda payload: target_window)
    monkeypatch.setattr(controller, "_active_window", lambda: target_window)
    monkeypatch.setattr(controller, "_focus_window", lambda window: None)
    monkeypatch.setattr(controller, "_try_computer_seat_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, "_windows_desktop_action", lambda action, payload: desktop_actions.append((action, payload)))
    monkeypatch.setattr(controller, "_capture_action_result_screenshot", lambda *args, **kwargs: {})

    result = controller.run(
        "computer.type",
        {"text": "hello", "app": "Google Chrome", "title": "LINE Chat"},
        yolo_mode=True,
    )

    assert result["executed"] is True
    assert result.get("is_error") is not True
    assert desktop_actions[0][0] == "computer.type"


def test_windows_window_listing_is_dpi_aware(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer

    controller = _controller(tmp_path)
    scripts = []
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(controller, "_run_powershell_capture", lambda script: scripts.append(script) or "[]")

    assert controller._windows_windows() == []
    assert scripts
    assert "SetProcessDPIAware" in scripts[0]
