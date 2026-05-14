from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.browser_cdp import (
    BrowserCDPDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ComputerCapabilities,
    ComputerTarget,
)


def test_browser_cdp_capabilities_are_background_dom_safe():
    driver = BrowserCDPDriver()
    caps = driver.capabilities()

    assert isinstance(caps, ComputerCapabilities)
    assert caps.can_dom_action is True
    assert caps.can_background_click is True
    assert caps.can_parallel_user_work is True
    assert caps.can_foreground_action is False


def test_browser_cdp_unavailable_without_endpoint(monkeypatch):
    monkeypatch.delenv("RUMI_BROWSER_CDP_ENDPOINT", raising=False)

    assert BrowserCDPDriver().is_available() is False


def test_browser_cdp_semantic_action_is_explicitly_unsupported():
    result = BrowserCDPDriver().semantic_action(ComputerTarget(kind="browser_tab"), intent="press Save")

    assert result.executed is False
    assert result.confidence == "not_supported"
    assert result.target_kind == "browser_tab"
