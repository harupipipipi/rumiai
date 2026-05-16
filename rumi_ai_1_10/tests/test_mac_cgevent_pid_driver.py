"""Tests for MacCGEventPidDriver – instantiation, PID required, experimental."""

from __future__ import annotations

import sys

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.mac_cgevent_pid import (
    MacCGEventPidDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ComputerCapabilities,
    ComputerTarget,
)


def test_instantiate():
    d = MacCGEventPidDriver()
    assert d.name == "mac_cgevent_pid"
    assert d.platform == "darwin"


def test_capabilities():
    d = MacCGEventPidDriver()
    caps = d.capabilities()
    assert isinstance(caps, ComputerCapabilities)
    assert caps.can_pid_event is d.is_available()
    assert caps.can_semantic_action is False


def test_click_no_pid():
    d = MacCGEventPidDriver()
    target = ComputerTarget(app="Test", pid=None)
    result = d.click(target, x=10, y=20)
    assert result.executed is False
    assert any("PID" in n for n in result.notes)


def test_type_text_no_pid():
    d = MacCGEventPidDriver()
    target = ComputerTarget(pid=None)
    result = d.type_text(target, text="hello")
    assert result.executed is False
    assert any("PID" in n for n in result.notes)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin-only")
def test_click_with_pid_confidence():
    d = MacCGEventPidDriver()
    # Use PID 1 (launchd) – won't actually click but tests the path
    target = ComputerTarget(pid=1)
    result = d.click(target, x=0, y=0)
    # Whether it succeeds depends on pyobjc availability
    assert result.confidence == "experimental" or result.executed is False


def test_is_available():
    d = MacCGEventPidDriver()
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.mac.cgevent import (
        cgevent_smoke_test,
    )

    assert d.is_available() is (sys.platform == "darwin" and cgevent_smoke_test().get("available") is True)


def test_scroll_posts_to_pid_helper(monkeypatch):
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.mac import cgevent

    calls = []
    monkeypatch.setattr(
        cgevent,
        "post_scroll_to_pid",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    result = MacCGEventPidDriver().scroll(
        ComputerTarget(pid=123),
        x=10,
        y=20,
        direction="up",
        clicks=4,
    )

    assert result.executed is True
    assert result.confidence == "experimental"
    assert calls == [{"pid": 123, "x": 10, "y": 20, "direction": "up", "clicks": 4}]


def test_cgevent_key_helper_rejects_unrepresentable_combo(monkeypatch):
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.mac import cgevent

    monkeypatch.setattr(cgevent.sys, "platform", "darwin")
    monkeypatch.setattr(cgevent, "_CG_AVAILABLE", True)
    monkeypatch.setattr(cgevent, "MODIFIER_FLAGS", {"cmd": 1})

    assert cgevent.post_key_to_pid(123, key_combo="hyper+s") is False
