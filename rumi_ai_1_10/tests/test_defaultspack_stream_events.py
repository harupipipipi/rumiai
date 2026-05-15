from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.stream.events import run_event, to_legacy_chat_stream_event  # noqa: E402


def test_content_delta_maps_to_legacy_delta():
    event = run_event(
        "content_delta",
        run_id="run_1",
        conversation_id="conv_1",
        seq=1,
        data={"delta": "hello"},
    )

    assert to_legacy_chat_stream_event(event) == {"type": "delta", "delta": "hello"}


def test_browser_state_snapshot_maps_to_legacy_event():
    event = run_event(
        "browser_state_snapshot",
        run_id="run_1",
        conversation_id="conv_1",
        seq=7,
        data={
            "snapshot": {"active_window": {"title": "Example"}},
            "active_window": {"title": "Example"},
        },
        tool_call_id="call_1",
        state_revision=7,
    )

    legacy = to_legacy_chat_stream_event(event)
    assert legacy["type"] == "browser_state_snapshot"
    assert legacy["tool_call_id"] == "call_1"
    assert legacy["state_revision"] == 7
    assert legacy["snapshot"] == {"active_window": {"title": "Example"}}
