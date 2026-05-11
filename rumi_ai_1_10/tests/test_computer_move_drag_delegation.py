"""Tests for move/drag delegation through ComputerSeatService."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ActionResult
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.service import ComputerSeatService
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.registry import DriverRegistry
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.base import ComputerDriver
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
    BrowserComputerController,
)


class MoveCapableDriver(ComputerDriver):
    @property
    def name(self):
        return "move_driver"

    @property
    def platform(self):
        return "darwin"

    def capabilities(self):
        return ComputerCapabilities()

    def observe(self, target):
        return ObserveResult()

    def click(self, target, x=0, y=0, button="left"):
        return ActionResult(action="click", driver="move_driver", executed=True)

    def type_text(self, target, text=""):
        return ActionResult(action="type_text", driver="move_driver", executed=True)

    def key(self, target, key_combo=""):
        return ActionResult(action="key", driver="move_driver", executed=True)

    def scroll(self, target, x=0, y=0, direction="down", clicks=3):
        return ActionResult(action="scroll", driver="move_driver", executed=True)

    def semantic_action(self, target, intent="", element_or_point=None):
        return ActionResult(action="semantic_action", driver="move_driver", executed=True)

    def move(self, target, x=0, y=0):
        return ActionResult(action="move", driver="move_driver", executed=True)

    def drag(self, target, x1=0, y1=0, x2=0, y2=0):
        return ActionResult(action="drag", driver="move_driver", executed=True)

    def is_available(self):
        return True


def test_service_move():
    reg = DriverRegistry()
    reg.register(MoveCapableDriver())
    svc = ComputerSeatService(reg)
    # Patch platform to "other" so get_driver_chain uses all registered drivers
    svc._platform = "linux"
    result = svc.move({"app": "Test"}, x=100, y=200)
    assert result["executed"] is True
    assert result["driver"] == "move_driver"


def test_service_drag():
    reg = DriverRegistry()
    reg.register(MoveCapableDriver())
    svc = ComputerSeatService(reg)
    svc._platform = "linux"
    result = svc.drag({"app": "Test"}, x1=10, y1=20, x2=30, y2=40)
    assert result["executed"] is True
    assert result["driver"] == "move_driver"


def test_move_not_supported_returns_clean_result():
    """Drivers that don't override move return not-supported."""
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.base import ComputerDriver
    # The base class move returns executed=False
    reg = DriverRegistry()

    class MinimalDriver(ComputerDriver):
        @property
        def name(self):
            return "minimal"

        @property
        def platform(self):
            return "darwin"

        def capabilities(self):
            return ComputerCapabilities()

        def observe(self, target):
            return ObserveResult()

        def click(self, target, x=0, y=0, button="left"):
            return ActionResult(executed=False)

        def type_text(self, target, text=""):
            return ActionResult(executed=False)

        def key(self, target, key_combo=""):
            return ActionResult(executed=False)

        def scroll(self, target, x=0, y=0, direction="down", clicks=3):
            return ActionResult(executed=False)

        def semantic_action(self, target, intent="", element_or_point=None):
            return ActionResult(executed=False)

        def is_available(self):
            return True

    reg.register(MinimalDriver())
    svc = ComputerSeatService(reg)
    svc._platform = "linux"
    result = svc.move({"app": "Test"}, x=100, y=200)
    assert result["executed"] is False


def test_controller_move_delegates(tmp_path):
    svc = MagicMock()
    svc.move.return_value = asdict(ActionResult(action="move", driver="mac_foreground", executed=True))
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": [], "available_drivers": [], "unavailable_drivers": []}
    ctrl = BrowserComputerController(artifact_root=tmp_path)
    ctrl._computer_seat = svc
    result = ctrl.run("computer.move", {"x": 100, "y": 200, "physical": True}, yolo_mode=True)
    assert result["executed"] is True
    svc.move.assert_called_once()


def test_controller_drag_delegates(tmp_path):
    svc = MagicMock()
    svc.drag.return_value = asdict(ActionResult(action="drag", driver="mac_foreground", executed=True))
    svc.doctor.return_value = {"platform": "darwin", "driver_chain_order": [], "available_drivers": [], "unavailable_drivers": []}
    ctrl = BrowserComputerController(artifact_root=tmp_path)
    ctrl._computer_seat = svc
    result = ctrl.run("computer.drag", {"x1": 10, "y1": 20, "x2": 30, "y2": 40, "physical": True}, yolo_mode=True)
    assert result["executed"] is True
    svc.drag.assert_called_once()
