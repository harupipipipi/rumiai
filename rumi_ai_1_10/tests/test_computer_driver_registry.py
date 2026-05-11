"""Tests for DriverRegistry – register, get_driver, get_driver_chain."""

from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer import DriverRegistry
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.registry import (
    MAC_DRIVER_ORDER,
    WINDOWS_DRIVER_ORDER,
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


class FakeDriver(ComputerDriver):
    def __init__(self, name_: str, platform_: str, available: bool = True):
        self._name = name_
        self._platform = platform_
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return self._platform

    def capabilities(self):
        return ComputerCapabilities()

    def observe(self, target):
        return ObserveResult()

    def click(self, target, x=0, y=0, button="left"):
        return ActionResult()

    def type_text(self, target, text=""):
        return ActionResult()

    def key(self, target, key_combo=""):
        return ActionResult()

    def scroll(self, target, x=0, y=0, direction="down", clicks=3):
        return ActionResult()

    def semantic_action(self, target, intent="", element_or_point=None):
        return ActionResult()

    def is_available(self) -> bool:
        return self._available


def test_register_and_get():
    reg = DriverRegistry()
    d = FakeDriver("test_driver", "darwin")
    reg.register(d)
    assert reg.get_driver("test_driver") is d
    assert reg.get_driver("nonexistent") is None


def test_mac_driver_order():
    reg = DriverRegistry()
    # Register in reverse order
    for name in reversed(MAC_DRIVER_ORDER):
        reg.register(FakeDriver(name, "darwin"))
    chain = reg.get_driver_chain("darwin")
    assert [d.name for d in chain] == MAC_DRIVER_ORDER


def test_windows_driver_order():
    reg = DriverRegistry()
    for name in reversed(WINDOWS_DRIVER_ORDER):
        reg.register(FakeDriver(name, "win32"))
    chain = reg.get_driver_chain("win32")
    assert [d.name for d in chain] == WINDOWS_DRIVER_ORDER


def test_unavailable_excluded():
    reg = DriverRegistry()
    reg.register(FakeDriver("mac_accessibility", "darwin", available=True))
    reg.register(FakeDriver("mac_apple_events", "darwin", available=False))
    reg.register(FakeDriver("mac_cgevent_pid", "darwin", available=True))
    chain = reg.get_driver_chain("darwin")
    names = [d.name for d in chain]
    assert "mac_apple_events" not in names
    assert "mac_accessibility" in names
    assert "mac_cgevent_pid" in names
