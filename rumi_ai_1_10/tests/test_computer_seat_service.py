"""Tests for ComputerSeatService – observe/click/type_text with mock drivers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer import (
    ComputerSeatService,
    DriverRegistry,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.base import (
    ComputerDriver,
)


class MockDriver(ComputerDriver):
    def __init__(self, name_: str = "mock", succeed: bool = True):
        self._name = name_
        self._succeed = succeed

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(can_semantic_action=True)

    def observe(self, target):
        return ObserveResult(platform="darwin", ax_tree={"mock": True})

    def click(self, target, x=0, y=0, button="left"):
        return ActionResult(action="click", driver=self._name, executed=self._succeed)

    def type_text(self, target, text=""):
        return ActionResult(action="type_text", driver=self._name, executed=self._succeed)

    def key(self, target, key_combo=""):
        return ActionResult(action="key", driver=self._name, executed=self._succeed)

    def scroll(self, target, x=0, y=0, direction="down", clicks=3):
        return ActionResult(action="scroll", driver=self._name, executed=self._succeed)

    def semantic_action(self, target, intent="", element_or_point=None):
        return ActionResult(action="semantic_action", driver=self._name, executed=self._succeed)

    def is_available(self) -> bool:
        return True


def _make_service(drivers):
    reg = DriverRegistry()
    for d in drivers:
        reg.register(d)
    svc = ComputerSeatService(reg)
    svc._platform = "test"  # Use generic platform so all registered drivers are in chain
    return svc


def test_observe_success():
    svc = _make_service([MockDriver("mock1")])
    result = svc.observe({"app": "Test"})
    assert result["ax_tree"] == {"mock": True}


def test_click_success_not_fallback():
    svc = _make_service([MockDriver("mock1")])
    result = svc.click({"app": "Test"}, x=10, y=20)
    assert result["executed"] is True
    assert result["is_fallback"] is False


def test_click_fallback_to_next_driver():
    d1 = MockDriver("fail_driver", succeed=False)
    d2 = MockDriver("ok_driver", succeed=True)
    svc = _make_service([d1, d2])
    result = svc.click({"app": "Test"})
    # d1 returns executed=False, so chain tries d2
    assert result["executed"] is True
    assert result["driver"] == "ok_driver"


def test_type_text_success():
    svc = _make_service([MockDriver("mock1")])
    result = svc.type_text({"app": "Test"}, text="hello")
    assert result["executed"] is True


def test_audit_logger_called():
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.audit import AuditLogger

    logger = AuditLogger(log_path="/dev/null")
    logger.record = MagicMock(return_value=None)
    reg = DriverRegistry()
    reg.register(MockDriver("mock1"))
    svc = ComputerSeatService(reg, audit_logger=logger)
    svc._platform = "darwin"
    svc.click({"app": "Test"})
    assert logger.record.called
