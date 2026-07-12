"""Tests for MacAccessibilityDriver – instantiation and capabilities."""

from __future__ import annotations

import sys

import pytest

from tobkiri_runtime.ecosystem.rumi_default_tools_pack.domain.computer.drivers.mac_accessibility import (
    MacAccessibilityDriver,
)
from tobkiri_runtime.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ComputerCapabilities,
)


def test_instantiate():
    d = MacAccessibilityDriver()
    assert d.name == "mac_accessibility"
    assert d.platform == "darwin"


def test_capabilities():
    d = MacAccessibilityDriver()
    caps = d.capabilities()
    assert isinstance(caps, ComputerCapabilities)
    assert caps.can_semantic_action is True
    assert caps.can_parallel_user_work is True
    assert caps.can_pid_event is False
    assert caps.can_capture_background_window is False


@pytest.mark.skipif(sys.platform == "darwin", reason="Only test non-darwin behavior")
def test_not_available_non_darwin():
    d = MacAccessibilityDriver()
    assert d.is_available() is False


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin-only test")
def test_is_available_darwin():
    # On darwin, availability depends on TCC; just verify no crash
    d = MacAccessibilityDriver()
    result = d.is_available()
    assert isinstance(result, bool)
