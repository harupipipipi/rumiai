from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_browser_use_action_mapper_preserves_legacy_names_and_adds_v2_refs():
    from domain.browser.actions import map_browser_use_action

    session = map_browser_use_action({"action": "session"})
    opened = map_browser_use_action({"action": "open_url", "url": "https://example.test"})
    legacy_click = map_browser_use_action({"action": "click", "x": 1, "y": 2})
    ref_click = map_browser_use_action({"action": "click", "ref_id": "ref-submit"})
    profile = map_browser_use_action({"action": "profile_create", "profile_id": "Work"})

    assert session["action"] == "browser.session.health"
    assert opened["action"] == "browser.tab.open"
    assert opened["payload"]["url"] == "https://example.test"
    assert legacy_click["action"] == "computer.click"
    assert legacy_click["requires_computer_use"] is True
    assert ref_click["action"] == "browser.ref.click"
    assert ref_click["requires_browser_v2"] is True
    assert profile["action"] == "browser.profile.create"


def test_computer_use_action_mapper_keeps_desktop_actions():
    from domain.browser.actions import map_computer_use_action

    mapped = map_computer_use_action({"action": "scroll", "amount": -3})

    assert mapped["action"] == "computer.scroll"
    assert mapped["payload"]["amount"] == -3
    assert mapped["requires_computer_use"] is True


def test_browser_use_manifest_preserves_legacy_actions_and_exposes_v2_actions():
    manifest = json.loads(
        (DEFAULTSPACK_ROOT / "extensions" / "tools" / "browser_use" / "manifest.json").read_text(encoding="utf-8")
    )
    enum = set(manifest["config"]["schema"]["parameters"]["properties"]["action"]["enum"])

    assert {"session", "open_url", "screenshot", "move", "click", "type", "key", "scroll"} <= enum
    assert {
        "profile_create",
        "start",
        "stop",
        "restart",
        "health",
        "tabs",
        "open_tab",
        "navigate",
        "snapshot",
        "click_ref",
    } <= enum
    properties = manifest["config"]["schema"]["parameters"]["properties"]
    assert properties["schema"]["enum"] == ["managed_chromium"]
    assert "session_id" in properties
    assert "tab_id" in properties
    assert "ref_id" in properties
