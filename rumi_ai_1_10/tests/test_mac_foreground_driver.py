from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers import foreground_io
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.mac_foreground import (
    MacForegroundFallbackDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.mac import helper
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget


def test_mac_foreground_click_activates_target_before_physical_action(monkeypatch):
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(helper, "get_frontmost_app", lambda: {"name": "Previous"})
    monkeypatch.setattr(helper, "activate_app", lambda app, pid=None: calls.append(("activate", (app, pid))) or True)
    monkeypatch.setattr(helper, "restore_app", lambda previous: calls.append(("restore", previous)) or True)
    monkeypatch.setattr(
        foreground_io,
        "click",
        lambda x, y, button, platform_name=None: calls.append(("click", (x, y, button, platform_name))),
    )

    result = MacForegroundFallbackDriver().click(
        ComputerTarget(app="Safari", pid=321),
        x=10,
        y=20,
        button="left",
    )

    assert result.executed is True
    assert result.requires_foreground is True
    assert result.uses_physical_input is True
    assert calls == [
        ("activate", ("Safari", 321)),
        ("click", (10, 20, "left", "darwin")),
        ("restore", {"name": "Previous"}),
    ]


def test_mac_foreground_fails_closed_when_activation_fails(monkeypatch):
    monkeypatch.setattr(helper, "get_frontmost_app", lambda: None)
    monkeypatch.setattr(helper, "activate_app", lambda app, pid=None: False)
    monkeypatch.setattr(
        foreground_io,
        "click",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not click without activation")),
    )

    result = MacForegroundFallbackDriver().click(ComputerTarget(app="Missing"), x=1, y=2)

    assert result.executed is False
    assert result.confidence == "failed"
    assert any("Could not activate" in note for note in result.notes)
