"""Tests for BrowserComputerController delegation to ComputerSeatService."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ObserveResult,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
    BrowserComputerController,
)


@pytest.fixture
def controller(tmp_path):
    return BrowserComputerController(artifact_root=tmp_path / "artifacts")


def _mock_service():
    svc = MagicMock()
    svc.click.return_value = asdict(ActionResult(action="click", driver="mac_accessibility", executed=True))
    svc.type_text.return_value = asdict(ActionResult(action="type_text", driver="mac_accessibility", executed=True))
    svc.key.return_value = asdict(ActionResult(action="key", driver="mac_accessibility", executed=True))
    svc.scroll.return_value = asdict(ActionResult(action="scroll", driver="mac_accessibility", executed=True))
    svc.move.return_value = asdict(ActionResult(action="move", driver="mac_accessibility", executed=True))
    svc.drag.return_value = asdict(ActionResult(action="drag", driver="mac_accessibility", executed=True))
    svc.observe.return_value = asdict(ObserveResult(platform="darwin"))
    svc.semantic_action.return_value = asdict(ActionResult(action="semantic_action", driver="mac_accessibility", executed=True))
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": ["mac_accessibility"], "available_drivers": [], "unavailable_drivers": []}
    return svc


def test_click_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.click", {"x": 100, "y": 200, "physical": True, "approval_token": "bypass"}, yolo_mode=True)
    assert result["executed"] is True
    assert result["action"] == "computer.click"
    svc.click.assert_called_once()


def test_type_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.type", {"text": "hello"}, yolo_mode=True)
    assert result["executed"] is True
    svc.type_text.assert_called_once()


def test_key_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.key", {"key": "enter"}, yolo_mode=True)
    assert result["executed"] is True
    svc.key.assert_called_once()
    assert svc.key.call_args.kwargs["key_combo"] == "enter"


def test_key_delegation_preserves_explicit_combo_and_modifiers(controller):
    svc = _mock_service()
    controller._computer_seat = svc

    controller.run("computer.key", {"key": "a", "modifiers": ["command"]}, yolo_mode=True)
    assert svc.key.call_args.kwargs["key_combo"] == "command+a"

    svc.key.reset_mock()
    controller._try_computer_seat_action("computer.key", {"key": "ignored", "key_combo": "cmd+l"})
    assert svc.key.call_args.kwargs["key_combo"] == "cmd+l"

    svc.key.reset_mock()
    controller._try_computer_seat_action("computer.key", {"key_combo": "retrun"})
    assert svc.key.call_args.kwargs["key_combo"] == "return"


def test_scroll_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.scroll", {"direction": "up", "clicks": 7}, yolo_mode=True)
    assert result["executed"] is True
    svc.scroll.assert_called_once()
    assert svc.scroll.call_args.kwargs["direction"] == "up"
    assert svc.scroll.call_args.kwargs["clicks"] == 7


def test_pid_event_key_uses_normalized_key_combo(controller):
    svc = _mock_service()
    controller._computer_seat = svc

    controller._computer_seat_pid_event(
        {"pid": 123, "action": "key", "key": "a", "modifiers": ["command"]},
        yolo_mode=True,
    )

    assert svc.key.call_args.kwargs["key_combo"] == "command+a"


def test_key_delegation_repeats_backspace_count(controller):
    svc = _mock_service()
    controller._computer_seat = svc

    result = controller.run("computer.backspace", {"count": 4, "include_screenshot": False}, yolo_mode=True)

    assert result["executed"] is True
    assert result["count"] == 4
    assert svc.key.call_count == 4
    assert all(call.kwargs["key_combo"] == "backspace" for call in svc.key.call_args_list)


def test_key_repeat_reports_executed_count_when_interrupted(controller):
    svc = _mock_service()
    svc.key.side_effect = [
        asdict(ActionResult(action="key", driver="mac_accessibility", executed=True)),
        asdict(ActionResult(action="key", driver="mac_accessibility", executed=False)),
    ]
    controller._computer_seat = svc

    result = controller.run("computer.key", {"key": "backspace", "count": 4, "include_screenshot": False}, yolo_mode=True)

    assert result["executed"] is True
    assert result["count"] == 1
    assert result["requested_count"] == 4
    assert svc.key.call_count == 2


def test_direct_browser_computer_aliases_are_normalized(controller, monkeypatch):
    clipboard = {"value": ""}
    monkeypatch.setattr(controller, "_system_clipboard_write", lambda value: clipboard.update(value=value))
    monkeypatch.setattr(controller, "_system_clipboard_read", lambda: clipboard["value"])

    write = controller.run("clipboard_set", {"value": "hello"}, yolo_mode=True)
    read = controller.run("clipboard_get", {}, yolo_mode=True)

    assert write["action"] == "computer.clipboard.write"
    assert read["action"] == "computer.clipboard.read"
    assert read["content"] == "hello"


def test_apple_script_key_combo_alias_and_repeat(controller):
    script = controller._apple_script("computer.key", {"key_combo": "retrun", "count": 2})

    assert "repeat 2 times" in script
    assert "key code 36" in script
    assert 'keystroke "retrun"' not in script


def test_observe_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.observe", {"app": "Safari"})
    assert result["action"] == "computer.observe"
    svc.observe.assert_called_once()


def test_doctor_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.doctor", {})
    assert result["action"] == "computer.doctor"
    svc.doctor.assert_called_once()


def test_capture_action_result_screenshot_labels_move_and_click_feedback(controller, tmp_path, monkeypatch):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"fake"
    model_path = tmp_path / "model.png"
    model_path.write_bytes(png_bytes)

    def fake_capture(path, payload):
        path.write_bytes(png_bytes)
        return {"supported": True, "platform": "Darwin", "target_window": None}

    monkeypatch.setattr(controller, "_capture_screenshot", fake_capture)
    monkeypatch.setattr(controller, "_apply_screenshot_crop", lambda path, payload, capture: {})
    monkeypatch.setattr(controller, "_model_screenshot_copy", lambda path: model_path)
    monkeypatch.setattr(
        controller,
        "_screenshot_result",
        lambda path, model_path, system, **kwargs: {"platform": system, "supported": True},
    )
    monkeypatch.setattr(controller, "_marker_preview_image", lambda model_path, result, marker=None, drag_marker=None: None)
    monkeypatch.setattr(controller, "_image_data_url", lambda path: "data:image/png;base64,ZmFrZQ==")
    monkeypatch.setattr(controller, "_remember_last_screenshot", lambda result: None)

    move_result = controller._capture_action_result_screenshot({"x": 10, "y": 20}, None, action_name="computer.move")
    click_result = controller._capture_action_result_screenshot({"x": 10, "y": 20}, {"x": 10, "y": 20}, action_name="computer.click")

    assert move_result["visual_feedback"]["type"] == "post_move_screenshot"
    assert move_result["visual_feedback"]["model_image_path"] == str(model_path)
    assert click_result["visual_feedback"]["type"] == "post_click_screenshot"
    assert click_result["visual_feedback"]["marker"] == {"x": 10, "y": 20}


def test_move_dry_run_does_not_return_visual_feedback(controller):
    result = controller.run("computer.move", {"x": 12, "y": 34, "dry_run": True, "include_screenshot": True}, yolo_mode=True)

    assert result["dry_run"] is True
    assert "visual_feedback" not in result


def test_computer_clipboard_read_and_write_actions(controller, monkeypatch):
    clipboard = {"value": "initial"}

    monkeypatch.setattr(controller, "_system_clipboard_read", lambda: clipboard["value"])
    monkeypatch.setattr(controller, "_system_clipboard_write", lambda value: clipboard.update(value=value))

    write = controller.run("computer.clipboard.write", {"value": "hello"}, yolo_mode=True)
    read = controller.run("computer.clipboard.read", {}, yolo_mode=True)
    clear = controller.run("computer.clipboard.clear", {}, yolo_mode=True)

    assert write["written"] is True
    assert write["length"] == 5
    assert read["content"] == "hello"
    assert clear["cleared"] is True
    assert clipboard["value"] == ""
