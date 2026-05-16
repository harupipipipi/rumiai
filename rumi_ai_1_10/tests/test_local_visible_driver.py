from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers import foreground_io
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.local_visible import (
    LocalVisibleDesktopDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget


def test_local_visible_click_uses_real_helper_before_success(monkeypatch):
    calls: list[tuple[int, int, str]] = []
    monkeypatch.setattr(foreground_io, "action_api_available", lambda platform_name=None: True)
    monkeypatch.setattr(foreground_io, "click", lambda x, y, button: calls.append((x, y, button)))

    result = LocalVisibleDesktopDriver().click(ComputerTarget(kind="desktop"), x=10, y=20, button="right")

    assert result.executed is True
    assert result.driver == "local_visible"
    assert result.requires_foreground is True
    assert result.uses_physical_input is True
    assert calls == [(10, 20, "right")]


def test_local_visible_action_fails_closed_without_platform_api(monkeypatch):
    monkeypatch.setattr(foreground_io, "action_api_available", lambda platform_name=None: False)

    result = LocalVisibleDesktopDriver().type_text(ComputerTarget(kind="desktop"), text="hello")

    assert result.executed is False
    assert result.confidence == "not_supported"
    assert result.requires_foreground is True
    assert any("No visible-screen automation API" in note for note in result.notes)


def test_local_visible_observe_uses_capture_helper_when_available(monkeypatch):
    monkeypatch.setattr(foreground_io, "action_api_available", lambda platform_name=None: True)
    monkeypatch.setattr(foreground_io, "capture_api_available", lambda platform_name=None: True)
    monkeypatch.setattr(
        foreground_io,
        "capture_visible_screen",
        lambda platform_name=None: {"method": "fake_capture", "data_url": "data:image/png;base64,AA=="},
    )

    result = LocalVisibleDesktopDriver().observe(ComputerTarget(app="VisibleApp", pid=123))

    assert result.screenshot["method"] == "fake_capture"
    assert result.capabilities["can_foreground_action"] is True
    assert result.capabilities["requires_foreground_for_capture"] is True


def test_local_visible_observe_fails_closed_without_capture_api(monkeypatch):
    monkeypatch.setattr(foreground_io, "action_api_available", lambda platform_name=None: False)
    monkeypatch.setattr(foreground_io, "capture_api_available", lambda platform_name=None: False)

    result = LocalVisibleDesktopDriver().observe(ComputerTarget(app="Missing"))

    assert result.screenshot["method"] == "unavailable"
    assert result.capabilities["can_foreground_action"] is False
    assert result.fallback_available is False
