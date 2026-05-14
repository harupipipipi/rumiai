"""Tests for Windows ComputerSeat drivers."""

from __future__ import annotations

import sys

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.windows_postmessage import (
    WindowsPostMessageDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.windows_uia import (
    WindowsUIADriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)


def test_windows_uia_instantiate():
    driver = WindowsUIADriver()
    assert driver.name == "windows_uia"
    assert driver.platform == "win32"


def test_windows_uia_capabilities():
    caps = WindowsUIADriver().capabilities()
    assert isinstance(caps, ComputerCapabilities)
    assert caps.can_semantic_action is True
    assert caps.can_capture_background_window is True
    assert caps.can_background_click is True
    assert caps.can_parallel_user_work is True


def test_windows_uia_is_available():
    driver = WindowsUIADriver()
    assert driver.is_available() is (sys.platform == "win32")


def test_windows_uia_methods_return_safe_results():
    driver = WindowsUIADriver()
    target = ComputerTarget(kind="window", app="DefinitelyMissingWindow")

    observe = driver.observe(target)
    assert isinstance(observe, ObserveResult)
    assert observe.platform == "win32"

    results = [
        driver.click(target),
        driver.type_text(target, text="hi"),
        driver.key(target, key_combo="ctrl+s"),
        driver.scroll(target),
        driver.semantic_action(target, intent="press Save"),
    ]
    for result in results:
        assert isinstance(result, ActionResult)
        assert result.executed is False
        assert result.driver == "windows_uia"


def test_windows_postmessage_instantiate():
    driver = WindowsPostMessageDriver()
    assert driver.name == "windows_postmessage"
    assert driver.platform == "win32"


def test_windows_postmessage_capabilities():
    caps = WindowsPostMessageDriver().capabilities()
    assert isinstance(caps, ComputerCapabilities)
    assert caps.can_pid_event is True
    assert caps.can_semantic_action is False
    assert caps.can_background_click is True
    assert caps.can_background_key is True


def test_windows_postmessage_is_available():
    driver = WindowsPostMessageDriver()
    assert driver.is_available() is (sys.platform == "win32")


def test_windows_postmessage_methods_return_safe_results():
    driver = WindowsPostMessageDriver()
    target = ComputerTarget(kind="window", app="DefinitelyMissingWindow")

    observe = driver.observe(target)
    assert isinstance(observe, ObserveResult)
    assert observe.platform == "win32"

    results = [
        driver.click(target),
        driver.type_text(target),
        driver.key(target),
        driver.scroll(target),
        driver.semantic_action(target),
    ]
    for result in results:
        assert isinstance(result, ActionResult)
        assert result.executed is False
        assert result.driver == "windows_postmessage"
