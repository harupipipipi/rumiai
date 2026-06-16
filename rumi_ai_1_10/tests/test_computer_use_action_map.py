"""Tests for computer_use/main.py action_map completeness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_funcs_dir = str(Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "functions")
if _funcs_dir not in sys.path:
    sys.path.insert(0, _funcs_dir)


EXPECTED_ACTIONS = [
    "screenshot", "click", "type", "key", "scroll", "context",
    "apps", "windows", "select_app", "select_window", "show_app", "move", "drag",
    "open_url", "browser_open_url",
    "clipboard", "clipboard_read", "clipboard_write", "clipboard_clear", "backspace",
    "observe", "semantic_action", "press", "pid_event", "doctor", "diagnose",
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


def test_computer_use_manifest_exposes_new_actions():
    manifest_path = Path(_funcs_dir).parent / "tools" / "computer_use" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actions = manifest["config"]["schema"]["parameters"]["properties"]["action"]["enum"]
    for action in ["observe", "semantic_action", "press", "pid_event", "doctor", "diagnose"]:
        assert action in actions


def test_browser_computer_manifest_exposes_new_actions():
    manifest_path = Path(_funcs_dir).parent / "tools" / "browser_computer" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actions = manifest["config"]["schema"]["parameters"]["properties"]["action"]["enum"]
    for action in [
        "computer.observe",
        "computer.semantic_action",
        "computer.press",
        "computer.pid_event",
        "computer.doctor",
        "computer.diagnose",
    ]:
        assert action in actions


def test_action_map_open_url_maps_to_browser_open_url(monkeypatch):
    from computer_use import main as computer_use_main

    captured = {}

    def fake_run_browser_computer(context, args):
        captured["context"] = context
        captured["args"] = args
        return {"status": "ok"}

    monkeypatch.setattr(computer_use_main, "_run_browser_computer", fake_run_browser_computer)

    result = computer_use_main.run(
        {"conversation_workspace_dir": "/tmp/workspace"},
        {"action": "open_url", "url": "https://example.com", "app": "Google Chrome"},
    )

    assert result == {"status": "ok"}
    assert captured["args"]["action"] == "browser.open_url"
    assert captured["args"]["payload"]["url"] == "https://example.com"
    assert captured["args"]["payload"]["app"] == "Google Chrome"


def test_action_map_browser_open_url_maps_correctly():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    assert '"browser_open_url": "browser.open_url"' in source


def test_action_map_preserves_clipboard_and_repeat_payload(monkeypatch):
    from computer_use import main as computer_use_main

    captured = {}

    def fake_run_browser_computer(context, args):
        captured["args"] = args
        return {"status": "ok"}

    monkeypatch.setattr(computer_use_main, "_run_browser_computer", fake_run_browser_computer)

    computer_use_main.run(
        {},
        {"action": "backspace", "count": 4, "key_combo": "retrun", "content": "hello"},
    )

    assert captured["args"]["action"] == "computer.backspace"
    assert captured["args"]["payload"]["count"] == 4
    assert captured["args"]["payload"]["key_combo"] == "retrun"
    assert captured["args"]["payload"]["content"] == "hello"
