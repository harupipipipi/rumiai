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


def test_scroll_delegates_to_seat(controller):
    svc = _mock_service()
    controller._computer_seat = svc
    result = controller.run("computer.scroll", {"direction": "down"}, yolo_mode=True)
    assert result["executed"] is True
    svc.scroll.assert_called_once()


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
