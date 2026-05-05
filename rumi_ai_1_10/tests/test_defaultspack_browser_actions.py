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


def test_computer_use_executor_payload_preserves_v2_fields():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "computer_use",
        {
            "action": "computer.app.focus",
            "app": "Vivaldi",
            "keys": ["cmd", "v"],
            "content": "hello",
        },
    )

    assert action == "computer.app.focus"
    assert payload["app"] == "Vivaldi"
    assert payload["keys"] == ["cmd", "v"]
    assert payload["content"] == "hello"


def test_zoom_executor_payload_uses_dedicated_computer_zoom_action():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "zoom",
        {"latest": True, "x": 10, "y": 20, "radius": 30, "scale": 2},
    )

    assert action == "computer.zoom"
    assert payload == {"latest": True, "x": 10, "y": 20, "radius": 30, "scale": 2}


def test_app_defaults_do_not_retarget_screenshot_based_clicks():
    from domain.tool.executor import _apply_tool_support_desktop_defaults, _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "computer_use",
        {"action": "click", "point": [825, 530]},
    )

    adjusted = _apply_tool_support_desktop_defaults(
        action,
        payload,
        {"chat_params": {"tool_support": {"default_target_app": "Vivaldi"}}},
    )

    assert adjusted["point"] == [825, 530]
    assert "target" not in adjusted
    assert "app" not in adjusted


def test_app_defaults_still_scope_app_screenshots():
    from domain.tool.executor import _apply_tool_support_desktop_defaults, _browser_computer_action_payload

    action, payload = _browser_computer_action_payload("computer_use", {"action": "screenshot"})

    adjusted = _apply_tool_support_desktop_defaults(
        action,
        payload,
        {"chat_params": {"tool_support": {"default_target_app": "Vivaldi"}}},
    )

    assert adjusted["target"] == "app"
    assert adjusted["app"] == "Vivaldi"
    assert adjusted["focus"] is True


def test_empty_frontend_default_target_app_is_replaced_by_text_inference():
    from blocks.chat.send import _with_inferred_tool_support

    updated = _with_inferred_tool_support(
        {
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Vivaldi で LINE Chat を開いているので computer_use で送信して",
                    }
                ],
            },
            "params": {"tool_support": {"default_target_app": ""}},
        }
    )

    assert updated["params"]["tool_support"]["default_target_app"] == "Vivaldi"


def test_browser_use_executor_reaches_browser_v2_profile_manager(tmp_path):
    from domain.tool.executor import _try_execute_browser_v2

    created = _try_execute_browser_v2(
        {"action": "profile_create", "profile_id": "Operator", "name": "Operator Browser"},
        {"browser_root": str(tmp_path)},
    )
    listed = _try_execute_browser_v2({"action": "profile_list"}, {"browser_root": str(tmp_path)})

    assert created["action"] == "browser.profile.create"
    assert created["profile"]["id"] == "operator"
    assert listed["active_profile_id"] == "operator"
    assert [profile["id"] for profile in listed["profiles"]] == ["operator"]


def test_browser_use_executor_reaches_browser_v2_session_actions(tmp_path):
    from domain.tool.executor import _try_execute_browser_v2

    started = _try_execute_browser_v2(
        {"action": "start", "profile_id": "Operator", "session_id": "session-operator", "launch": False},
        {"browser_root": str(tmp_path)},
    )
    health = _try_execute_browser_v2(
        {"action": "health", "profile_id": "Operator", "session_id": "session-operator"},
        {"browser_root": str(tmp_path)},
    )

    assert started["action"] == "browser.session.start"
    assert started["id"] == "session-operator"
    assert health["action"] == "browser.session.health"
    assert health["session"]["id"] == "session-operator"


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


def test_zoom_manifest_exposes_gemma_friendly_inspection_tool():
    manifest = json.loads(
        (DEFAULTSPACK_ROOT / "extensions" / "tools" / "zoom" / "manifest.json").read_text(encoding="utf-8")
    )
    properties = manifest["config"]["schema"]["parameters"]["properties"]

    assert manifest["id"] == "zoom"
    assert manifest["config"]["name"] == "zoom"
    assert manifest["config"]["requires_approval"] is False
    assert {"x", "y", "width", "height", "radius", "scale", "source_path", "latest"} <= set(properties)
