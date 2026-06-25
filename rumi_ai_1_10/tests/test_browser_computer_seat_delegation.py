"""Tests for BrowserComputerController delegation to ComputerSeatService."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
for path in (ROOT, DEFAULTSPACK_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ObserveResult,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
    BrowserComputerController,
)


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "computer seat delegation")
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path / "user_data"))
    instance = BrowserComputerController(artifact_root=tmp_path / "artifacts")
    shared = tmp_path / "user_data" / "shared"
    instance._session_path = shared / "browser_sessions.json"
    instance._approval_path = shared / "browser_computer_approvals.json"
    instance._browser_root = shared / "browser"
    instance._profile_root = instance._browser_root / "profiles"
    return instance


def _mock_service():
    svc = MagicMock()
    safe_result_kwargs = {
        "can_parallel_user_work": True,
        "requires_foreground": False,
        "uses_physical_input": False,
    }
    svc.click.return_value = asdict(ActionResult(action="click", driver="mac_accessibility", executed=True, **safe_result_kwargs))
    svc.type_text.return_value = asdict(ActionResult(action="type_text", driver="mac_accessibility", executed=True, confidence="high", **safe_result_kwargs))
    svc.key.return_value = asdict(ActionResult(action="key", driver="mac_accessibility", executed=True, confidence="high", **safe_result_kwargs))
    svc.scroll.return_value = asdict(ActionResult(action="scroll", driver="mac_accessibility", executed=True, confidence="high", **safe_result_kwargs))
    svc.move.return_value = asdict(ActionResult(action="move", driver="mac_accessibility", executed=True))
    svc.drag.return_value = asdict(ActionResult(action="drag", driver="mac_accessibility", executed=True))
    svc.observe.return_value = asdict(ObserveResult(platform="darwin"))
    svc.semantic_action.return_value = asdict(ActionResult(action="semantic_action", driver="mac_accessibility", executed=True))
    svc.background_action.side_effect = lambda action, target, payload, **kwargs: {
        "type_text": svc.type_text.return_value,
        "key": svc.key.return_value,
        "scroll": svc.scroll.return_value,
        "click": svc.click.return_value,
    }.get(action, asdict(ActionResult(action=action, driver="none", executed=False)))
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": ["mac_accessibility"], "available_drivers": [], "unavailable_drivers": []}
    return svc


def _approval_token_for(controller: BrowserComputerController, action: str, payload: dict) -> str:
    request = controller.run(action, payload)
    token = str(request.get("approval_token") or "")
    if token:
        return token
    approval_module = getattr(controller, "_approval_module", lambda: None)()
    assert approval_module is not None
    approval_args = {"action": action, "payload": payload}
    approval = approval_module.create_approval_request(
        action,
        "high",
        approval_args,
        details={"action": action, "pack_id": "defaultspack"},
    )
    decision = approval_module.approve(approval["request_id"])
    return str(decision["token"])


def test_click_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run(
        "computer.click",
        {
            "x": 100,
            "y": 200,
            "physical": True,
            "approval_token": "bypass",
            "include_screenshot": False,
        },
        yolo_mode=True,
    )
    assert result["executed"] is True
    assert result["action"] == "computer.click"
    svc.click.assert_called_once()


def test_type_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run(
        "computer.type",
        {"text": "hello", "include_screenshot": False},
        yolo_mode=True,
    )
    assert result["executed"] is True
    svc.background_action.assert_called_once()
    assert svc.background_action.call_args.args[0] == "type_text"


def test_key_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run(
        "computer.key",
        {"key": "enter", "include_screenshot": False},
        yolo_mode=True,
    )
    assert result["executed"] is True
    svc.background_action.assert_called_once()
    assert svc.background_action.call_args.args[0] == "key"


def test_scroll_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run(
        "computer.scroll",
        {"direction": "down", "include_screenshot": False},
        yolo_mode=True,
    )
    assert result["executed"] is True
    svc.background_action.assert_called_once()
    assert svc.background_action.call_args.args[0] == "scroll"


def test_observe_requires_approval_without_yolo(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.observe", {"app": "Safari"})
    assert result.get("requires_approval") is True
    svc.observe.assert_not_called()


def test_observe_delegates_to_seat_with_yolo(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.observe", {"app": "Safari"}, yolo_mode=True)
    assert result["action"] == "computer.observe"
    svc.observe.assert_called_once()


def test_observe_delegates_to_seat_with_approval(controller):
    svc = _mock_service()
    payload = {"app": "Safari"}
    token = _approval_token_for(controller, "computer.observe", payload)
    controller._computer_seat = svc
    result = controller.run("computer.observe", {**payload, "approval_token": token})
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
