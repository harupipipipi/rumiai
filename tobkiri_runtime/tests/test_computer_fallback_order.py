"""Tests for fallback chain behavior – 3 mock drivers."""

from __future__ import annotations

from tobkiri_runtime.ecosystem.rumi_default_tools_pack.domain.computer import (
    ComputerSeatService,
    DriverRegistry,
)
from tobkiri_runtime.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)
from tobkiri_runtime.ecosystem.rumi_default_tools_pack.domain.computer.drivers.base import (
    ComputerDriver,
)


class FallbackDriver(ComputerDriver):
    def __init__(self, name_: str, succeed: bool = False, raise_exc: bool = False):
        self._name = name_
        self._succeed = succeed
        self._raise = raise_exc

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self):
        return ComputerCapabilities()

    def observe(self, target):
        return ObserveResult()

    def click(self, target, x=0, y=0, button="left"):
        if self._raise:
            raise RuntimeError(f"{self._name} error")
        return ActionResult(action="click", driver=self._name, executed=self._succeed)

    def type_text(self, target, text=""):
        if self._raise:
            raise RuntimeError(f"{self._name} error")
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


def test_first_fails_second_succeeds():
    d1 = FallbackDriver("d1", succeed=False)
    d2 = FallbackDriver("d2", succeed=True)
    d3 = FallbackDriver("d3", succeed=True)
    svc = _make_service([d1, d2, d3])
    result = svc.click({"app": "Test"})
    assert result["executed"] is True
    assert result["driver"] == "d2"
    # is_fallback is True because d1 returned executed=False first
    assert result["is_fallback"] is True


def test_first_raises_second_succeeds():
    d1 = FallbackDriver("d1", raise_exc=True)
    d2 = FallbackDriver("d2", succeed=True)
    d3 = FallbackDriver("d3", succeed=False)
    svc = _make_service([d1, d2, d3])
    result = svc.click({"app": "Test"})
    assert result["executed"] is True
    assert result["driver"] == "d2"


def test_all_fail():
    d1 = FallbackDriver("d1", succeed=False)
    d2 = FallbackDriver("d2", succeed=False)
    d3 = FallbackDriver("d3", succeed=False)
    svc = _make_service([d1, d2, d3])
    result = svc.click({"app": "Test"})
    assert result["executed"] is False
    assert "notes" in result


def test_all_raise():
    d1 = FallbackDriver("d1", raise_exc=True)
    d2 = FallbackDriver("d2", raise_exc=True)
    d3 = FallbackDriver("d3", raise_exc=True)
    svc = _make_service([d1, d2, d3])
    result = svc.click({"app": "Test"})
    assert result["executed"] is False
    assert len(result["notes"]) == 3
    assert "d1 error" in result["notes"][0]
