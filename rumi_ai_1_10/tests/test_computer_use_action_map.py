"""Tests for computer_use/main.py action_map completeness."""

from __future__ import annotations

import sys
from pathlib import Path
import importlib.util

import pytest

_funcs_dir = str(Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "functions")
if _funcs_dir not in sys.path:
    sys.path.insert(0, _funcs_dir)


EXPECTED_ACTIONS = [
    "screenshot", "click", "type", "key", "scroll", "context",
    "apps", "windows", "select_app", "select_window", "show_app", "move", "drag",
    "open_url", "browser_open_url", "open",
    "monitors", "list_monitors", "displays", "list_displays", "select_monitor",
    "set_monitor", "switch_monitor", "window_monitor",
    "observe", "semantic_action", "press", "pid_event", "doctor", "diagnose",
    "backspace", "delete_back", "clipboard", "clipboard_read", "clipboard_get",
    "clipboard_write", "clipboard_set", "clipboard_clear",
]


def test_action_map_keys_exist():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    for action in EXPECTED_ACTIONS:
        assert f'"{action}"' in source, f"action_map missing key: {action}"


def test_action_map_observe_maps_correctly():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    assert '"observe": "computer.observe"' in source


def test_action_map_semantic_action_maps_correctly():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    assert '"semantic_action": "computer.semantic_action"' in source


def test_action_map_press_maps_to_semantic_action():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    assert '"press": "computer.semantic_action"' in source


def test_action_map_doctor_maps_correctly():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    assert '"doctor": "computer.doctor"' in source
    assert '"diagnose": "computer.doctor"' in source


def test_action_map_open_url_maps_to_browser_open_url():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    assert '"open_url": "browser.open_url"' in source
    assert '"browser_open_url": "browser.open_url"' in source


def test_browser_computer_function_prefers_pack_local_domain_import():
    main_path = Path(_funcs_dir) / "browser_computer" / "main.py"
    source = main_path.read_text()
    assert "spec_from_file_location" in source
    assert '"domain" / "tool" / "browser_computer.py"' in source


def test_pid_event_target_fields_pass_through():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    for field in ('"pid"', '"window_id"', '"window_title"', '"hwnd"', '"sub_action"', '"action_type"', '"key_combo"', '"direction"', '"clicks"'):
        assert field in source


def test_monitor_target_fields_pass_through():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    for field in ('"monitor"', '"monitor_id"', '"monitor_index"', '"display_id"', '"display_index"', '"screen_id"'):
        assert field in source


def test_computer_use_clipboard_and_repeat_fields_pass_through():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    for field in ('"count"', '"times"', '"repeat"', '"content"', '"value"'):
        assert field in source


def test_computer_use_run_preserves_window_and_scroll_payload(monkeypatch):
    module_path = Path(_funcs_dir) / "computer_use" / "main.py"
    spec = importlib.util.spec_from_file_location("computer_use_main_for_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    original_sys_path = list(sys.path)
    spec.loader.exec_module(module)
    sys.path[:] = original_sys_path
    captured = {}

    def fake_run_browser_computer(context, args):
        captured["context"] = context
        captured["args"] = args
        return {"status": "ok", "data": {"ok": True}}

    monkeypatch.setattr(module, "_run_browser_computer", fake_run_browser_computer)

    result = module.run(
        {"conversation_workspace_dir": "/tmp/workspace"},
        {
            "action": "pid_event",
            "pid": 123,
            "window_id": 456,
            "hwnd": 789,
            "window_title": "Google Gemini",
            "monitor_id": "darwin:2",
            "monitor_index": 1,
            "display_id": "2",
            "sub_action": "scroll",
            "action_type": "scroll",
            "key_combo": "cmd+l",
            "direction": "up",
            "clicks": 7,
            "count": 3,
            "content": "hello",
            "value": "clipboard fallback",
        },
    )

    assert result == {"status": "ok", "data": {"ok": True}}
    assert captured["args"]["action"] == "computer.pid_event"
    payload = captured["args"]["payload"]
    assert payload["pid"] == 123
    assert payload["window_id"] == 456
    assert payload["hwnd"] == 789
    assert payload["window_title"] == "Google Gemini"
    assert payload["monitor_id"] == "darwin:2"
    assert payload["monitor_index"] == 1
    assert payload["display_id"] == "2"
    assert payload["sub_action"] == "scroll"
    assert payload["action_type"] == "scroll"
    assert payload["key_combo"] == "cmd+l"
    assert payload["direction"] == "up"
    assert payload["clicks"] == 7
    assert payload["count"] == 3
    assert payload["content"] == "hello"
    assert payload["value"] == "clipboard fallback"
