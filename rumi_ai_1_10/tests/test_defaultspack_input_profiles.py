from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.input_profile_registry import InputProfileRegistry  # noqa: E402
from domain.external.input_profile_engine import InputProfileEngine  # noqa: E402
from domain.external.normalizer import normalize_line_event  # noqa: E402


def test_line_default_profile_maps_text_message_to_user_input():
    event = normalize_line_event(
        {
            "type": "message",
            "webhookEventId": "evt",
            "source": {"type": "user", "userId": "U123"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
            "replyToken": "reply",
        },
        verified=True,
    )
    profile = InputProfileRegistry(DEFAULTSPACK_ROOT).get("line.default")
    envelope = InputProfileEngine(profile).to_envelope(event)

    assert envelope.role == "user"
    assert envelope.input == "hello"
    assert envelope.source["provider"] == "line"
    assert envelope.metadata["line"]["reply_token"] == "reply"


def test_line_default_profile_fallbacks_non_text_message():
    event = normalize_line_event(
        {
            "type": "message",
            "webhookEventId": "evt",
            "source": {"type": "user", "userId": "U123"},
            "message": {"id": "m1", "type": "image"},
        },
        verified=True,
    )
    profile = InputProfileRegistry(DEFAULTSPACK_ROOT).get("line.default")
    envelope = InputProfileEngine(profile).to_envelope(event)

    assert envelope.input == "LINE image message received. messageId=m1"
