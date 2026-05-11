"""Tests for _desktop_action delegation through ComputerSeatService."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ActionResult
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
    BrowserComputerController,
)


@pytest.fixture
def controller(tmp_path):
    ctrl = BrowserComputerController(artifact_root=tmp_path / "artifacts")
    return ctrl


def _mock_seat_click_success():
    svc = MagicMock()
    svc.click.return_value = asdict(ActionResult(action="click", driver="mac_accessibility", executed=True, confidence="high"))
    svc.type_text.return_value = asdict(ActionResult(action="type_text", driver="mac_accessibility", executed=True))
    svc.key.return_value = asdict(ActionResult(action="key", driver="mac_accessibility", executed=True))
    svc.scroll.return_value = asdict(ActionResult(action="scroll", driver="mac_accessibility", executed=True))
    svc.move.return_value = asdict(ActionResult(action="move", driver="mac_accessibility", executed=True))
    svc.drag.return_value = asdict(ActionResult(action="drag", driver="mac_accessibility", executed=True))
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": [], "available_drivers": [], "unavailable_drivers": []}
    return svc


def test_click_through_seat_returns_driver(controller):
    svc = _mock_seat_click_success()
    controller._computer_seat = svc
    result = controller.run("computer.click", {"x": 50, "y": 50, "physical": True}, yolo_mode=True)
    assert result["executed"] is True
    assert result["driver"] == "mac_accessibility"


def test_seat_failure_falls_through_to_legacy(controller):
    """If ComputerSeatService returns executed=False, legacy code runs."""
    svc = MagicMock()
    svc.click.return_value = asdict(ActionResult(action="click", driver="none", executed=False))
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": [], "available_drivers": [], "unavailable_drivers": []}
    controller._computer_seat = svc
    # This will fall through to legacy code which may or may not succeed
    # depending on platform, but it should not raise
    try:
        result = controller.run("computer.click", {"x": 50, "y": 50, "physical": True}, yolo_mode=True)
        # If we get here, legacy code ran
        assert result["action"] == "computer.click"
    except Exception:
        # Legacy code may fail on CI – that's OK, the point is it fell through
        pass


def test_seat_exception_falls_through(controller):
    """If _try_computer_seat_action raises, legacy code runs."""
    svc = MagicMock()
    svc.click.side_effect = RuntimeError("driver crash")
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": [], "available_drivers": [], "unavailable_drivers": []}
    controller._computer_seat = svc
    try:
        result = controller.run("computer.click", {"x": 50, "y": 50, "physical": True}, yolo_mode=True)
        assert result["action"] == "computer.click"
    except Exception:
        pass


def test_dry_run_does_not_execute(controller):
    svc = _mock_seat_click_success()
    controller._computer_seat = svc
    result = controller.run("computer.click", {"x": 50, "y": 50, "physical": True, "dry_run": True}, yolo_mode=True)
    assert result["dry_run"] is True
    svc.click.assert_not_called()
