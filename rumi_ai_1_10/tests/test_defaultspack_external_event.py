from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.normalizer import normalize_discord_message, normalize_line_event  # noqa: E402


def test_line_group_user_room_normalization():
    event = normalize_line_event(
        {
            "type": "message",
            "webhookEventId": "evt-1",
            "source": {"type": "group", "groupId": "C123", "userId": "U123"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
        destination="dest",
    )

    assert event.provider == "line"
    assert event.workspace.as_dict() == {"type": "line_destination", "id": "dest"}
    assert event.scope.as_dict() == {"type": "group", "id": "C123"}
    assert event.actor.as_dict() == {"type": "user", "id": "U123"}
    assert event.conversation.id == "line:group:C123"
    assert event.event["id"] == "evt-1"
    assert event.event["message_id"] == "m1"
    assert event.verified is True


def test_external_event_as_dict_redacts_tokens():
    event = normalize_line_event(
        {
            "type": "message",
            "webhookEventId": "evt-1",
            "replyToken": "reply-secret",
            "source": {"type": "user", "userId": "U123"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
        destination="dest",
    )

    public_event = event.as_dict()
    assert public_event["payload"]["replyToken"] == "***"
    assert public_event["metadata"]["reply_token"] == "***"
    assert event.as_dict(redact=False)["payload"]["replyToken"] == "reply-secret"


def test_discord_guild_channel_user_normalization():
    event = normalize_discord_message(
        {
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "m1",
                "guild_id": "g1",
                "channel_id": "c1",
                "content": "hello",
                "author": {"id": "u1"},
            },
        },
        verified=True,
    )

    assert event.provider == "discord"
    assert event.workspace.as_dict() == {"type": "guild", "id": "g1"}
    assert event.scope.as_dict() == {"type": "channel", "id": "c1"}
    assert event.actor.as_dict() == {"type": "user", "id": "u1"}
    assert event.event["message_id"] == "m1"
