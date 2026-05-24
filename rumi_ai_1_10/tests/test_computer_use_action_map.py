"""Tests for computer_use/main.py action_map completeness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_funcs_dir = str(Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "functions")
if _funcs_dir not in sys.path:
    sys.path.insert(0, _funcs_dir)


EXPECTED_ACTIONS = [
    "screenshot", "click", "type", "key", "scroll", "context",
    "apps", "windows", "select_app", "select_window", "show_app", "move", "drag",
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


def test_pid_event_target_fields_pass_through():
    main_path = Path(_funcs_dir) / "computer_use" / "main.py"
    source = main_path.read_text()
    for field in ('"pid"', '"window_id"', '"window_title"', '"hwnd"', '"sub_action"', '"key_combo"'):
        assert field in source
