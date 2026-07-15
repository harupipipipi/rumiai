from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.input_profile_engine import InputProfileEngine  # noqa: E402
from domain.external.input_profile_registry import InputProfileRegistry  # noqa: E402
from domain.external.normalizer import normalize_slack_event  # noqa: E402


def test_slack_default_profile_maps_event_text_and_source_context_default():
    event = normalize_slack_event(
        {
            "team_id": "T123",
            "event_id": "Ev1",
            "event": {
                "type": "message",
                "channel": "C123",
                "user": "U123",
                "text": "hello slack",
                "ts": "1710000000.0001",
            },
        },
        verified=True,
    )
    profile = InputProfileRegistry(DEFAULTSPACK_ROOT).get("slack.default")
    envelope = InputProfileEngine(profile).to_envelope(event)

    assert envelope.input == "hello slack"
    assert envelope.source["provider"] == "slack"
    assert envelope.params["external_input"]["default_response"]["include_source_context"] is True
    assert envelope.metadata["slack"]["channel_id"] == "C123"
