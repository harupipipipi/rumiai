"""Tests for the 4 fixes in the additional fix pass."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.base import ComputerDriver
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.registry import DriverRegistry
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.service import ComputerSeatService
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
    BrowserComputerController,
)


# ---------------------------------------------------------------------------
# Test 1: _get_computer_seat lazy import works without monkeypatching
# ---------------------------------------------------------------------------

def test_get_computer_seat_lazy_import(tmp_path):
    """_get_computer_seat should work via relative import without pre-setting _computer_seat."""
    ctrl = BrowserComputerController(artifact_root=tmp_path)
    # Should not raise – uses from ..computer.factory import
    svc = ctrl._get_computer_seat()
    assert svc is not None
    # Second call returns same instance
    assert ctrl._get_computer_seat() is svc


# ---------------------------------------------------------------------------
# Test 2: observe aggregates screenshot + ax_tree from different drivers
# ---------------------------------------------------------------------------

class ScreenshotOnlyDriver(ComputerDriver):
    @property
    def name(self):
        return "screenshot_driver"

    @property
    def platform(self):
        return "test"

    def capabilities(self):
        return ComputerCapabilities(can_capture_background_window=True)

    def observe(self, target):
        return ObserveResult(
            platform="test",
            screenshot={"path": "/tmp/shot.png", "width": 1920, "height": 1080},
        )

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


class AXTreeOnlyDriver(ComputerDriver):
    @property
    def name(self):
        return "ax_driver"

    @property
    def platform(self):
        return "test"

    def capabilities(self):
        return ComputerCapabilities(can_semantic_action=True, can_parallel_user_work=True)

    def observe(self, target):
        return ObserveResult(
            platform="test",
            ax_tree={"root": {"role": "AXWindow", "children": []}},
        )

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


def test_observe_aggregates_screenshot_and_ax_tree():
    """observe should combine screenshot from one driver and ax_tree from another."""
    reg = DriverRegistry()
    reg.register(ScreenshotOnlyDriver())
    reg.register(AXTreeOnlyDriver())
    svc = ComputerSeatService(reg)
    svc._platform = "test"

    result = svc.observe({"app": "Test"})

    assert result["screenshot"]["path"] == "/tmp/shot.png"
    assert result["ax_tree"]["root"]["role"] == "AXWindow"
    # Merged capabilities from both drivers
    assert result["capabilities"]["can_capture_background_window"] is True
    assert result["capabilities"]["can_semantic_action"] is True
    assert result["capabilities"]["can_parallel_user_work"] is True


# ---------------------------------------------------------------------------
# Test 3: pid_event respects payload["action"]
# ---------------------------------------------------------------------------

def test_pid_event_accepts_payload_action(tmp_path):
    """_computer_seat_pid_event should use payload['action'] as sub-action."""
    ctrl = BrowserComputerController(artifact_root=tmp_path)
    svc = MagicMock()
    svc.key.return_value = asdict(ActionResult(action="key", driver="mock", executed=True))
    ctrl._computer_seat = svc

    result = ctrl._computer_seat_pid_event(
        {"pid": 123, "action": "key", "key_combo": "cmd+s"},
        yolo_mode=True,
    )
    assert result["action"] == "computer.pid_event"
    svc.key.assert_called_once()


def test_pid_event_sub_action_takes_priority(tmp_path):
    """sub_action should take priority over action."""
    ctrl = BrowserComputerController(artifact_root=tmp_path)
    svc = MagicMock()
    svc.type_text.return_value = asdict(ActionResult(action="type_text", driver="mock", executed=True))
    ctrl._computer_seat = svc

    result = ctrl._computer_seat_pid_event(
        {"pid": 123, "sub_action": "type_text", "action": "click", "text": "hi"},
        yolo_mode=True,
    )
    svc.type_text.assert_called_once()


def test_pid_event_passes_window_target_fields(tmp_path):
    """pid_event should preserve explicit window targeting for browser popups."""
    ctrl = BrowserComputerController(artifact_root=tmp_path)
    svc = MagicMock()
    svc.click.return_value = asdict(ActionResult(action="click", driver="mock", executed=True))
    ctrl._computer_seat = svc

    ctrl._computer_seat_pid_event(
        {
            "window_id": 68926,
            "hwnd": 68926,
            "app": "chrome",
            "title": "Google Gemini",
            "sub_action": "click",
            "x": 10,
            "y": 20,
        },
        yolo_mode=True,
    )

    target = svc.click.call_args.args[0]
    assert target["window_id"] == 68926
    assert target["hwnd"] == 68926
    assert target["app"] == "chrome"
    assert target["window_title"] == "Google Gemini"


# ---------------------------------------------------------------------------
# Test 4: high-risk manifests declare approval/risk metadata
# ---------------------------------------------------------------------------

_MANIFEST_DIR = Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "functions"


def test_semantic_action_manifest_has_approval():
    manifest = json.loads((_MANIFEST_DIR / "computer_semantic_action" / "manifest.json").read_text())
    assert manifest["requires_approval"] is True
    assert manifest["risk_level"] == "high"
    assert "capabilities" in manifest


def test_pid_event_manifest_has_approval():
    manifest = json.loads((_MANIFEST_DIR / "computer_pid_event" / "manifest.json").read_text())
    assert manifest["requires_approval"] is True
    assert manifest["risk_level"] == "high"
    assert "capabilities" in manifest
