from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.chat.store import ChatStore  # noqa: E402
from domain.external.adapters.discord import DiscordResponseAdapter  # noqa: E402
from domain.external.adapters.slack import SlackResponseAdapter  # noqa: E402
from domain.external.chat_link import CHAT_LINK_PROMPT, handle_chat_link_message  # noqa: E402
from domain.external.normalizer import normalize_slack_event  # noqa: E402
from domain.external.source_store import ExternalSourceStore  # noqa: E402


def _set_chat_link_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTERNAL_SOURCES_PATH", str(tmp_path / "external_sources.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))


def _discord_message(content: str, *, message_id: str = "m1") -> dict[str, Any]:
    return {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": message_id,
            "guild_id": "G1",
            "channel_id": "C1",
            "content": content,
            "author": {"id": "U1"},
        },
    }


def _slack_message(text: str, *, event_id: str = "E1", ts: str = "111.1") -> dict[str, Any]:
    return {
        "type": "event_callback",
        "team_id": "T1",
        "event_id": event_id,
        "event": {
            "type": "message",
            "channel": "C1",
            "user": "U1",
            "ts": ts,
            "text": text,
        },
    }


def test_discord_unlinked_message_prompts_for_chatid(monkeypatch, tmp_path):
    from blocks.integrations import discord as discord_block  # noqa: E402

    _set_chat_link_paths(monkeypatch, tmp_path)
    sent_plans: list[dict[str, Any]] = []
    monkeypatch.setattr(discord_block, "_verify_discord", lambda headers, raw_body: {"ok": True, "verified": True})
    monkeypatch.setattr(
        discord_block,
        "dispatch_external_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dispatch should wait for chatid link")),
    )
    monkeypatch.setattr(
        DiscordResponseAdapter,
        "send",
        lambda self, plan, event=None, context=None: sent_plans.append(plan) or {"sent": True},
    )

    result = discord_block.run(_discord_message("hello"), {})

    data = result["data"]
    saved = ExternalSourceStore().get("discord", "channel", "C1")
    assert data["status"] == "ok"
    assert data["assistant_text"] == CHAT_LINK_PROMPT
    assert data["external_chat_link"]["action"] == "prompt"
    assert sent_plans[0]["messages"][0]["text"] == CHAT_LINK_PROMPT
    assert saved is not None
    assert saved["enabled"] is False


def test_discord_plain_chatid_links_then_dispatches_to_linked_chat(monkeypatch, tmp_path):
    from blocks.integrations import discord as discord_block  # noqa: E402

    _set_chat_link_paths(monkeypatch, tmp_path)
    conversation = ChatStore().create_conversation(model="stub/default")
    conversation = ChatStore().update_conversation(conversation["id"], {"title": "Discord Link"}) or conversation
    sent_plans: list[dict[str, Any]] = []
    captured: dict[str, Any] = {}
    monkeypatch.setattr(discord_block, "_verify_discord", lambda headers, raw_body: {"ok": True, "verified": True})
    monkeypatch.setattr(
        DiscordResponseAdapter,
        "send",
        lambda self, plan, event=None, context=None: sent_plans.append(plan) or {"sent": True},
    )

    link_result = discord_block.run(_discord_message(conversation["id"], message_id="m-link"), {})

    saved = ExternalSourceStore().get("discord", "channel", "C1")
    assert link_result["data"]["external_chat_link"]["action"] == "linked"
    assert saved["linked_conversation_id"] == conversation["id"]
    assert saved["enabled"] is True

    def fake_dispatch(event, *, input_profile_id, audience_policy, context, send_response, envelope_overrides=None):
        captured["event"] = event
        captured["context"] = context
        captured["envelope_overrides"] = envelope_overrides
        return {
            "status": "ok",
            "assistant_text": "done",
            "response_plan": {"provider": "discord", "messages": [{"type": "text", "text": "done"}]},
        }

    monkeypatch.setattr(discord_block, "dispatch_external_event", fake_dispatch)

    result = discord_block.run(_discord_message("hello after link", message_id="m2"), {})

    assert result["data"]["status"] == "ok"
    assert captured["context"]["conversation_id"] == conversation["id"]
    assert captured["envelope_overrides"] == {"target": {"conversation_id": conversation["id"], "direct": True}}
    assert sent_plans[-1]["messages"][0]["text"] == "done"


def test_slack_unlinked_message_prompts_for_chatid(monkeypatch, tmp_path):
    from blocks.integrations import slack as slack_block  # noqa: E402

    _set_chat_link_paths(monkeypatch, tmp_path)
    sent_plans: list[dict[str, Any]] = []
    monkeypatch.setattr(slack_block, "_verify_slack", lambda headers, raw_body: {"ok": True, "verified": True})
    monkeypatch.setattr(
        slack_block,
        "dispatch_external_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dispatch should wait for chatid link")),
    )
    monkeypatch.setattr(
        SlackResponseAdapter,
        "send",
        lambda self, plan, event=None, context=None: sent_plans.append(plan) or {"sent": True},
    )

    result = slack_block.run(_slack_message("hello"), {})

    data = result["data"]
    saved = ExternalSourceStore().get("slack", "channel", "C1")
    assert data["status"] == "ok"
    assert data["assistant_text"] == CHAT_LINK_PROMPT
    assert data["external_chat_link"]["action"] == "prompt"
    assert sent_plans[0]["messages"][0]["text"] == CHAT_LINK_PROMPT
    assert saved is not None
    assert saved["enabled"] is False


def test_slack_plain_chatid_links_then_dispatches_to_linked_chat(monkeypatch, tmp_path):
    from blocks.integrations import slack as slack_block  # noqa: E402

    _set_chat_link_paths(monkeypatch, tmp_path)
    conversation = ChatStore().create_conversation(model="stub/default")
    conversation = ChatStore().update_conversation(conversation["id"], {"title": "Slack Link"}) or conversation
    sent_plans: list[dict[str, Any]] = []
    captured: dict[str, Any] = {}
    monkeypatch.setattr(slack_block, "_verify_slack", lambda headers, raw_body: {"ok": True, "verified": True})
    monkeypatch.setattr(
        SlackResponseAdapter,
        "send",
        lambda self, plan, event=None, context=None: sent_plans.append(plan) or {"sent": True},
    )

    link_result = slack_block.run(_slack_message(conversation["id"], event_id="E-link", ts="111.1"), {})

    saved = ExternalSourceStore().get("slack", "channel", "C1")
    assert link_result["data"]["external_chat_link"]["action"] == "linked"
    assert saved["linked_conversation_id"] == conversation["id"]
    assert saved["enabled"] is True

    def fake_dispatch(event, *, input_profile_id, audience_policy, context, send_response, envelope_overrides=None):
        captured["event"] = event
        captured["context"] = context
        captured["envelope_overrides"] = envelope_overrides
        return {
            "status": "ok",
            "assistant_text": "done",
            "response_plan": {"provider": "slack", "messages": [{"type": "text", "text": "done"}]},
        }

    monkeypatch.setattr(slack_block, "dispatch_external_event", fake_dispatch)

    result = slack_block.run(_slack_message("hello after link", event_id="E2", ts="222.2"), {})

    assert result["data"]["status"] == "ok"
    assert captured["context"]["conversation_id"] == conversation["id"]
    assert captured["envelope_overrides"] == {"target": {"conversation_id": conversation["id"], "direct": True}}
    assert sent_plans[-1]["messages"][0]["text"] == "done"


def test_chat_link_commands_resolve_from_shared_slash_command_registry(monkeypatch, tmp_path):
    _set_chat_link_paths(monkeypatch, tmp_path)
    conversation = ChatStore().create_conversation(model="stub/default")
    event = normalize_slack_event(_slack_message(f"/switch {conversation['id']}"), verified=True)

    result = handle_chat_link_message(
        event,
        {},
        f"/switch {conversation['id']}",
        command_action_resolver=lambda name: "line_change_chat" if name == "switch" else "",
    )

    assert result is not None
    assert result["external_chat_link"]["action"] == "linked"
    assert result["external_chat_link"]["conversation_id"] == conversation["id"]
