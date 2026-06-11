from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_browser_companion_background_supports_search_home_candidate_navigation():
    background = (
        DEFAULTSPACK_ROOT
        / "browser_extensions"
        / "rumi_browser_companion"
        / "background.js"
    ).read_text(encoding="utf-8")

    assert "rumi:search-home:set-route-state" in background
    assert "rumi:search-home:advance-candidate" in background
    assert "SEARCH_HOME_ROUTE_STATE_KEY" in background
    assert 'chrome.tabs.update(tabId, { url })' in background


def test_browser_companion_content_script_captures_search_home_hotkeys():
    content = (
        DEFAULTSPACK_ROOT
        / "browser_extensions"
        / "rumi_browser_companion"
        / "content_script.js"
    ).read_text(encoding="utf-8")

    assert 'window.addEventListener("message"' in content
    assert 'type: "rumi:search-home:set-route-state"' in content
    assert 'window.addEventListener(\n    "keydown"' in content
    assert 'event.key === "ArrowRight"' in content
    assert 'event.key === "ArrowLeft"' in content
    assert 'event.key === "Enter"' in content
