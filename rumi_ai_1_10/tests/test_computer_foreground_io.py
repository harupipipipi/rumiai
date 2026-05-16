from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers import foreground_io
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.local_visible import (
    LocalVisibleDesktopDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget


def test_foreground_io_reports_unavailable_on_unsupported_platform():
    assert foreground_io.action_api_available("linux") is False
    assert foreground_io.capture_api_available("linux") is False

    try:
        foreground_io.click(1, 2, platform_name="linux")
    except foreground_io.ForegroundAutomationUnavailable as exc:
        assert "supported only" in str(exc)
    else:
        raise AssertionError("foreground_io.click pretended to execute on linux")


def test_local_visible_driver_fails_closed_without_action_api(monkeypatch):
    driver = LocalVisibleDesktopDriver()
    target = ComputerTarget(kind="screen")

    monkeypatch.setattr(foreground_io, "action_api_available", lambda platform_name=None: False)

    result = driver.click(target, x=10, y=20)

    assert result.executed is False
    assert result.confidence == "not_supported"
    assert result.uses_physical_input is True


def test_local_visible_driver_reports_success_only_after_action_call(monkeypatch):
    calls = []
    driver = LocalVisibleDesktopDriver()
    target = ComputerTarget(kind="screen")

    monkeypatch.setattr(foreground_io, "action_api_available", lambda platform_name=None: True)
    monkeypatch.setattr(foreground_io, "click", lambda x, y, button="left": calls.append((x, y, button)))

    result = driver.click(target, x=10, y=20, button="right")

    assert result.executed is True
    assert result.confidence == "high"
    assert calls == [(10, 20, "right")]


def test_windows_key_and_text_are_escaped_before_sendkeys(monkeypatch):
    scripts = []

    monkeypatch.setattr(foreground_io, "_powershell_executable", lambda: "pwsh")
    monkeypatch.setattr(foreground_io, "_run_powershell", scripts.append)

    foreground_io.key("ctrl+s", platform_name="win32")
    foreground_io.type_text("a+b{c}", platform_name="win32")

    assert "SendWait('^s')" in scripts[0]
    assert "SendWait('a{+}b{{}c{}}')" in scripts[1]
