from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.browser_cdp import (
    BrowserCDPDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ComputerCapabilities,
    ComputerTarget,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.browser.cdp_client import (
    BrowserCDPClient,
    CDPTab,
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


def test_browser_cdp_key_combo_preserves_modifiers(monkeypatch):
    calls = []
    client = BrowserCDPClient(endpoint="http://127.0.0.1:9222")
    tab = CDPTab(id="1", title="Test", url="https://example.test", web_socket_debugger_url="ws://example")
    monkeypatch.setattr(client, "call", lambda tab_arg, method, params=None: calls.append((method, params)) or {})

    client.press_key_combo(tab, "ctrl+shift+p")

    assert calls[0] == ("Input.dispatchKeyEvent", {"type": "keyDown", "key": "P", "modifiers": 10})
    assert calls[1] == ("Input.dispatchKeyEvent", {"type": "keyUp", "key": "P", "modifiers": 10})


def test_browser_cdp_empty_type_and_bad_scroll_fail_closed():
    client = BrowserCDPClient(endpoint="http://127.0.0.1:9222")
    tab = CDPTab(id="1", title="Test", url="https://example.test", web_socket_debugger_url="ws://example")

    try:
        client.type_text(tab, "")
    except ValueError as exc:
        assert "No text" in str(exc)
    else:
        raise AssertionError("empty CDP typing must fail closed")

    try:
        client.scroll(tab, 0, 0, "diagonal", 1)
    except ValueError as exc:
        assert "Unsupported CDP scroll direction" in str(exc)
    else:
        raise AssertionError("unsupported CDP scroll direction must fail closed")
