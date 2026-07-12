from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_conversation_steer_queues_and_processes_followup(monkeypatch, tmp_path):
    from blocks.conversation.steer import run as steer
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_STEER_STORE_PATH", str(tmp_path / "steer.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    conversation = ChatStore().create_conversation(model="stub/default")
    calls: list[dict] = []

    def fake_send(payload, context):
        calls.append({"payload": payload, "context": context})
        return {"status": "ok", "data": {"id": "assistant-steer"}}

    monkeypatch.setattr("blocks.chat.send.run", fake_send)
    queued = steer({"conversation_id": conversation["id"], "prompt": "next step"}, {})

    processed = steer({"action": "process", "conversation_id": conversation["id"]}, {})

    assert queued["status"] == "ok"
    assert processed["status"] == "ok"
    assert processed["data"]["processed"][0]["status"] == "sent"
    assert calls[0]["payload"]["message"]["content"] == "next step"
    assert calls[0]["context"]["_conversation_steer_autosend"] is True


def test_conversation_steer_can_be_consumed_for_running_turn(monkeypatch, tmp_path):
    from blocks.conversation.steer import run as steer
    from domain.chat.steer import ConversationSteerStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_STEER_STORE_PATH", str(tmp_path / "steer.json"))

    queued = steer({"conversation_id": "conv-1", "prompt": "change course"}, {})
    consumed = ConversationSteerStore().consume_for_conversation("conv-1")
    processed = steer({"action": "process", "conversation_id": "conv-1"}, {})

    assert queued["status"] == "ok"
    assert consumed[0]["status"] == "injected"
    assert consumed[0]["prompt"] == "change course"
    assert processed["status"] == "ok"
    assert processed["data"]["processed"] == []


def test_conversation_steer_consume_respects_auto_send_false(monkeypatch, tmp_path):
    from blocks.conversation.steer import run as steer
    from domain.chat.steer import ConversationSteerStore
    from domain.chat.stream_engine import ChatRunEngine

    monkeypatch.setenv("RUMI_DEFAULTSPACK_STEER_STORE_PATH", str(tmp_path / "steer.json"))

    queued = steer({"conversation_id": "conv-1", "prompt": "do not auto inject", "auto_send": False}, {})
    working_messages: list[dict] = [{"role": "user", "content": "original request"}]

    events = list(ChatRunEngine()._inject_conversation_steer("conv-1", working_messages))
    remaining = ConversationSteerStore().list(status="queued")

    assert queued["status"] == "ok"
    assert queued["data"]["auto_send"] is False
    assert events == []
    assert working_messages == [{"role": "user", "content": "original request"}]
    assert len(remaining) == 1
    assert remaining[0]["status"] == "queued"
    assert remaining[0]["prompt"] == "do not auto inject"


def test_conversation_handoff_creates_move_card_without_initial_send(monkeypatch, tmp_path):
    from blocks.conversation.handoff import run as handoff

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))

    result = handoff({"model": "stub/default", "prompt": "seed", "send": False, "conversation_id": "source-1"}, {})

    assert result["status"] == "ok"
    data = result["data"]
    assert data["conversation_id"]
    assert data["widget"]["kind"] == "conversation_handoff"
    assert data["widget"]["url_path"] == f"?chat={data['conversation_id']}"
    assert data["external_reply"]["handoff_token"] == data["conversation_id"]
