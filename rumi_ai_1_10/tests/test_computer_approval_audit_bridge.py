"""Tests for approval and audit bridge between BrowserComputerController and ComputerSeatService."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ActionResult
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.permissions import (
    requires_approval,
    risk_level,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
    BrowserComputerController,
)


@pytest.fixture
def controller(tmp_path):
    ctrl = BrowserComputerController(artifact_root=tmp_path / "artifacts")
    svc = MagicMock()
    svc.click.return_value = asdict(ActionResult(action="click", driver="mock", executed=True))
    svc.type_text.return_value = asdict(ActionResult(action="type_text", driver="mock", executed=True))
    svc.semantic_action.return_value = asdict(ActionResult(action="semantic_action", driver="mock", executed=True))
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": [], "available_drivers": [], "unavailable_drivers": []}
    ctrl._computer_seat = svc
    return ctrl


def test_click_requires_approval_without_yolo(controller):
    """click without yolo_mode or a trusted approval token should require approval."""
    result = controller.run("computer.click", {"x": 50, "y": 50})
    assert result.get("requires_approval") is True
    assert "approval_token" not in result


def test_click_executes_with_yolo(controller):
    """click with yolo_mode should execute without approval."""
    result = controller.run("computer.click", {"x": 50, "y": 50}, yolo_mode=True)
    assert result["executed"] is True


def test_semantic_action_requires_approval(controller):
    """semantic_action is high-risk and requires approval."""
    result = controller.run("computer.semantic_action", {"intent": "press Save"})
    assert result.get("requires_approval") is True


def test_semantic_action_yolo_bypasses(controller):
    """semantic_action with yolo_mode bypasses approval."""
    result = controller.run("computer.semantic_action", {"intent": "press Save"}, yolo_mode=True)
    assert result["action"] == "computer.semantic_action"
    assert result.get("requires_approval") is not True


def test_pid_event_requires_approval(controller):
    """pid_event is high-risk and requires approval."""
    result = controller.run("computer.pid_event", {"pid": 123, "sub_action": "click", "x": 10, "y": 10})
    assert result.get("requires_approval") is True


def test_pid_event_yolo_bypasses(controller):
    """pid_event with yolo_mode bypasses approval."""
    result = controller.run("computer.pid_event", {"pid": 123, "sub_action": "click", "x": 10, "y": 10}, yolo_mode=True)
    assert result["action"] == "computer.pid_event"


def test_dry_run_does_not_execute_driver(controller):
    """dry_run should not call any driver method."""
    result = controller.run("computer.click", {"x": 50, "y": 50, "dry_run": True}, yolo_mode=True)
    assert result["dry_run"] is True
    controller._computer_seat.click.assert_not_called()


# --- Permission model tests ---

def test_click_is_high_risk():
    assert risk_level("click") == "high"
    assert requires_approval("click") is True


def test_observe_is_low_risk():
    assert risk_level("observe") == "low"
    assert requires_approval("observe") is False


def test_scroll_is_medium_risk():
    assert risk_level("scroll") == "medium"
    assert requires_approval("scroll") is False


def test_move_is_medium_risk():
    assert risk_level("move") == "medium"
    assert requires_approval("move") is False


def test_drag_is_high_risk():
    assert risk_level("drag") == "high"
    assert requires_approval("drag") is True


def test_semantic_action_is_high_risk():
    assert risk_level("semantic_action") == "high"
    assert requires_approval("semantic_action") is True


def test_semantic_action_function_routes_through_approval_router(monkeypatch):
    """Standalone semantic function must not call ComputerSeatService directly."""
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.functions.computer_semantic_action import main

    captured = {}

    def fake_run_computer_action(action, payload, context, **kwargs):
        captured["action"] = action
        captured["payload"] = payload
        captured["context"] = context
        captured["kwargs"] = kwargs
        return {"action": action, "requires_approval": True}

    monkeypatch.setattr(main, "run_computer_action", fake_run_computer_action)

    result = main.run(
        {"conversation_id": "conv-1"},
        {"app": "VictimApp", "intent": "press Delete", "element_id": "AX-DESTRUCTIVE-BUTTON"},
    )

    assert result["requires_approval"] is True
    assert captured["action"] == "computer.semantic_action"
    assert captured["payload"] == {
        "app": "VictimApp",
        "pid": None,
        "window_id": None,
        "intent": "press Delete",
        "element_id": "AX-DESTRUCTIVE-BUTTON",
    }
    assert captured["kwargs"]["tool_name"] == "computer_semantic_action"
    assert captured["kwargs"]["yolo_mode"] is False
