from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.chat.browser_state import (  # noqa: E402
    BrowserStateLimits,
    BrowserStateNormalizer,
    emit_browser_state_events,
)


_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aKkAAAAASUVORK5CYII="
)


def _window(app: str, title: str, x: int, y: int, width: int, height: int, *, active: bool = False, window_id: int = 17):
    return {
        "app": app,
        "title": title,
        "x": str(x),
        "y": str(y),
        "width": str(width),
        "height": str(height),
        "active": active,
        "window_id": str(window_id),
        "capture_rect": {"x": x + 1, "y": y + 2, "width": width - 10, "height": height - 10},
    }


def test_browser_state_normalizer_emits_invalidated_and_screenshot_for_browser_computer_feedback():
    result = {
        "action": "computer.click",
        "executed": True,
        "screenshot_path": "/tmp/post-click.png",
        "model_image_path": "/tmp/post-click-model.png",
        "data_url": _PNG_DATA_URL,
        "mime_type": "image/png",
        "image_size": {"width": 1280, "height": 720},
        "target_window": _window("Safari", "Docs", 100, 120, 1280, 720, active=True, window_id=31),
        "active_window": _window("Safari", "Docs", 100, 120, 1280, 720, active=True, window_id=31),
        "selected_window": _window("Safari", "Docs", 100, 120, 1280, 720, window_id=31),
        "visual_feedback": {
            "type": "post_click_screenshot",
            "screenshot_path": "/tmp/post-click.png",
            "model_image_path": "/tmp/post-click-model.png",
            "data_url": _PNG_DATA_URL,
            "marker": {"x": 10, "y": 20, "coordinate_space": "normalized_1000"},
        },
        "widget": {
            "data_url": _PNG_DATA_URL,
            "model_image_path": "/tmp/widget-model.png",
        },
    }

    normalizer = BrowserStateNormalizer()
    emission = normalizer.emit_from_tool_result(
        "browser_computer",
        result,
        tool_call_id="call_click_1",
    )

    assert [event["event"] for event in emission.events] == ["invalidated", "screenshot"]
    assert emission.state_revision == 2
    assert normalizer.state_revision == 2

    invalidated_event, screenshot_event = emission.events
    assert invalidated_event["state_revision"] == 1
    assert invalidated_event["invalidated"]["scope"] == "visible_ui"
    assert invalidated_event["invalidated"]["window"]["window_id"] == 31

    screenshot = screenshot_event["screenshot"]
    assert screenshot_event["state_revision"] == 2
    assert screenshot["action"] == "computer.click"
    assert screenshot["feedback_type"] == "post_click_screenshot"
    assert screenshot["path"] == "/tmp/post-click.png"
    assert screenshot["model_image_path"] == "/tmp/post-click-model.png"
    assert screenshot["sources"] == ["visual_feedback", "result", "widget"]
    assert screenshot["marker"] == {"x": 10, "y": 20, "coordinate_space": "normalized_1000"}
    assert screenshot["target_window"]["app"] == "Safari"
    assert screenshot["target_window"]["window_id"] == 31


def test_browser_state_normalizer_unwraps_tool_executor_envelope_for_visual_feedback():
    browser_result = {
        "action": "computer.click",
        "executed": True,
        "visual_feedback": {
            "type": "post_click_screenshot",
            "screenshot_path": "/tmp/post-click.png",
            "model_image_path": "/tmp/post-click-model.png",
            "data_url": _PNG_DATA_URL,
        },
        "target_window": _window("Chrome", "Docs", 0, 0, 1280, 720, window_id=42),
    }
    wrapped = {
        "status": "ok",
        "data": {
            "result": "browser_computer computer.click completed",
            "is_error": False,
            "widget": {"type": "browser_computer", **browser_result},
        },
    }

    emission = emit_browser_state_events(
        "browser_computer",
        wrapped,
        tool_call_id="call_browser_1",
        action="computer.click",
    )

    assert [event["event"] for event in emission.events] == ["invalidated", "screenshot"]
    screenshot = emission.events[-1]["screenshot"]
    assert screenshot["feedback_type"] == "post_click_screenshot"
    assert screenshot["model_image_path"] == "/tmp/post-click-model.png"
    assert screenshot["target_window"]["window_id"] == 42


def test_browser_state_preserves_large_data_url_without_truncating():
    data_url = "data:image/png;base64," + ("A" * 5000)
    emission = emit_browser_state_events(
        "browser_computer",
        {"action": "computer.click", "executed": True, "data_url": data_url},
    )

    screenshot = emission.events[-1]["screenshot"]
    assert screenshot["data_url"] == data_url
    assert not screenshot["data_url"].endswith("...")


def test_emit_browser_state_events_normalizes_snapshot_and_bounds_windows():
    result = {
        "action": "computer.context",
        "browser_session": {
            "last_url": "https://example.com",
            "active_profile_id": "default",
            "last_opened_with_managed_profile": True,
        },
        "active_window": _window("Google Chrome", "Example", 0, 0, 1440, 900, active=True, window_id=10),
        "selected_window": _window("Google Chrome", "Example", 0, 0, 1440, 900, window_id=10),
        "windows": [
            _window("Google Chrome", "Example", 0, 0, 1440, 900, active=True, window_id=10),
            _window("Slack", "Standup", 50, 50, 1100, 700, window_id=22),
        ],
        "cursor": {"x": 222, "y": 333, "origin": "top_left"},
    }

    emission = emit_browser_state_events(
        "browser_computer",
        result,
        state_revision=10,
        limits=BrowserStateLimits(max_windows=1),
    )

    assert emission.state_revision == 11
    assert [event["event"] for event in emission.events] == ["snapshot"]

    event = emission.events[0]
    snapshot = event["snapshot"]
    assert event["state_revision"] == 11
    assert snapshot["browser_session"]["last_url"] == "https://example.com"
    assert snapshot["active_window"]["window_id"] == 10
    assert snapshot["selected_window"]["app"] == "Google Chrome"
    assert snapshot["cursor"] == {"x": 222, "y": 333, "origin": "top_left"}
    assert len(snapshot["windows"]) == 1
    assert snapshot["windows_omitted"] == 1


def test_browser_state_normalizer_emits_bounded_dom_snapshot_and_merged_capture():
    result = {
        "action": "page.snapshot",
        "snapshot": {
            "url": "https://example.com",
            "title": "Example",
            "nodes": [
                {"element_id": "el-1", "text": "Open", "selector": "button.open"},
                {"element_id": "el-2", "text": "Search", "selector": "input.search"},
                {"element_id": "el-3", "text": "Footer", "selector": "footer"},
            ],
        },
        "path": "/tmp/browser-capture.png",
        "data_url": _PNG_DATA_URL,
        "image_size": {"width": 640, "height": 360},
        "capture": {
            "data_url": _PNG_DATA_URL,
            "target_window": _window("Microsoft Edge", "Example", 0, 0, 1280, 720, active=True, window_id=77),
        },
    }

    normalizer = BrowserStateNormalizer(state_revision=2, limits=BrowserStateLimits(max_dom_nodes=2))
    emission = normalizer.emit_from_tool_result(
        "browser_companion",
        result,
        tool_call_id="call_dom_1",
        timestamp=123,
    )

    assert [event["event"] for event in emission.events] == ["dom_snapshot", "screenshot"]
    assert emission.state_revision == 4

    dom_event, screenshot_event = emission.events
    assert dom_event["state_revision"] == 3
    assert dom_event["timestamp"] == 123
    assert dom_event["dom_snapshot"]["url"] == "https://example.com"
    assert dom_event["dom_snapshot"]["node_count"] == 3
    assert len(dom_event["dom_snapshot"]["nodes"]) == 2
    assert dom_event["dom_snapshot"]["nodes_omitted"] == 1
    assert dom_event["dom_snapshot"]["truncated"] is True

    screenshot = screenshot_event["screenshot"]
    assert screenshot_event["state_revision"] == 4
    assert screenshot["path"] == "/tmp/browser-capture.png"
    assert screenshot["sources"] == ["result", "capture"]
    assert screenshot["target_window"]["app"] == "Microsoft Edge"
    assert screenshot["target_window"]["window_id"] == 77
