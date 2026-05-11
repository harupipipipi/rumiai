"""Tests for Windows driver skeletons – instantiation and capabilities."""

from __future__ import annotations

import sys

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.windows_uia import (
    WindowsUIADriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.windows_postmessage import (
    WindowsPostMessageDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ComputerCapabilities,
    ComputerTarget,
)


def test_windows_uia_instantiate():
    d = WindowsUIADriver()
    assert d.name == "windows_uia"
    assert d.platform == "win32"


def test_windows_uia_capabilities():
    d = WindowsUIADriver()
    caps = d.capabilities()
    assert isinstance(caps, ComputerCapabilities)
    assert caps.can_semantic_action is True
    assert caps.can_capture_background_window is True


def test_windows_uia_is_available():
    d = WindowsUIADriver()
    if sys.platform == "win32":
        assert d.is_available() is True
    else:
        assert d.is_available() is False


def test_windows_uia_methods_raise():
    d = WindowsUIADriver()
    target = ComputerTarget(app="Notepad")
    with pytest.raises(NotImplementedError):
        d.observe(target)
    with pytest.raises(NotImplementedError):
        d.click(target)
    with pytest.raises(NotImplementedError):
        d.type_text(target, text="hi")
    with pytest.raises(NotImplementedError):
        d.key(target, key_combo="ctrl+s")
    with pytest.raises(NotImplementedError):
        d.scroll(target)
    with pytest.raises(NotImplementedError):
        d.semantic_action(target, intent="press Save")


def test_windows_postmessage_instantiate():
    d = WindowsPostMessageDriver()
    assert d.name == "windows_postmessage"
    assert d.platform == "win32"


def test_windows_postmessage_capabilities():
    d = WindowsPostMessageDriver()
    caps = d.capabilities()
    assert isinstance(caps, ComputerCapabilities)
    assert caps.can_pid_event is True
    assert caps.can_semantic_action is False


def test_windows_postmessage_is_available():
    d = WindowsPostMessageDriver()
    if sys.platform == "win32":
        assert d.is_available() is True
    else:
        assert d.is_available() is False


def test_windows_postmessage_methods_raise():
    d = WindowsPostMessageDriver()
    target = ComputerTarget(app="Notepad")
    with pytest.raises(NotImplementedError):
        d.observe(target)
    with pytest.raises(NotImplementedError):
        d.click(target)
    with pytest.raises(NotImplementedError):
        d.type_text(target)
    with pytest.raises(NotImplementedError):
        d.key(target)
    with pytest.raises(NotImplementedError):
        d.scroll(target)
    with pytest.raises(NotImplementedError):
        d.semantic_action(target)
