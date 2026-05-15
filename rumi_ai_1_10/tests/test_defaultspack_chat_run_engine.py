from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_send_and_stream_wrappers_consume_same_engine_final_message(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run as send_run
    from blocks.chat.stream import run as stream_run
    from domain.chat.stream_engine import ChatRunEngine

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    final_message = {
        "id": "assistant-1",
        "role": "assistant",
        "content": [{"type": "text", "text": "shared final"}],
        "raw_text": "shared final",
        "created_at": 1,
        "conversation_id": conversation["id"],
    }

    def fake_stream(self, input_data, context, *, stream_mode=True):
        yield {
            "type": "assistant_message_completed",
            "data": {"message": final_message},
        }
        yield {
            "type": "done",
            "data": {"message": final_message},
        }

    monkeypatch.setattr(ChatRunEngine, "stream", fake_stream)

    send_result = send_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello"},
            "tools": [],
        },
        {},
    )
    stream_result = stream_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello"},
            "tools": [],
        },
        {},
    )

    assert send_result["status"] == "ok"
    assert send_result["data"]["raw_text"] == "shared final"
    stream_events = list(stream_result["events"])
    assert stream_events[-2]["type"] == "message"
    assert stream_events[-1]["type"] == "done"
    assert stream_events[-1]["message"]["raw_text"] == "shared final"
    ChatStore._instance = None


def test_chat_send_and_stream_wrappers_write_inspector_logs(tmp_path, monkeypatch):
    from blocks.chat.send import run as send_run
    import blocks.chat.stream as stream_module
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.dev.inspector import Inspector

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    Inspector().clear()

    class FakeClient:
        def complete(self, model, messages, tools=None, params=None):
            return {
                "content": [{"type": "text", "text": "hello"}],
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

        def supports_stream(self, model):
            return True

        def stream(self, model, messages, tools=None, params=None):
            yield {"type": "content_delta", "delta": {"type": "text", "text": "hello"}}
            yield {"type": "stream_end", "finish_reason": "stop", "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}

    monkeypatch.setattr(engine_module, "AIClient", FakeClient)
    monkeypatch.setattr(stream_module, "AIClient", FakeClient)

    store = ChatStore()
    send_conversation = store.create_conversation(model="stub/default")
    send_result = send_run(
        {
            "conversation_id": send_conversation["id"],
            "message": {"role": "user", "content": "send hello"},
            "tools": [],
        },
        {},
    )
    assert send_result["status"] == "ok"
    send_log = Inspector().get_latest()
    assert send_log["conversation_id"] == send_conversation["id"]
    assert send_log["context_info"]["source"] == "blocks.chat.send"
    assert send_log["context_info"]["knowledge_results"] == []
    assert send_log["context_info"]["memory_results"] == []

    stream_conversation = store.create_conversation(model="stub/default")
    stream_result = stream_module.run(
        {
            "conversation_id": stream_conversation["id"],
            "message": {"role": "user", "content": "stream hello"},
            "tools": [],
        },
        {},
    )
    events = list(stream_result["events"])
    assert events[-1]["type"] == "done"
    stream_log = Inspector().get_latest()
    assert stream_log["conversation_id"] == stream_conversation["id"]
    assert stream_log["context_info"]["source"] == "blocks.chat.stream"
    assert stream_log["context_info"]["message_count"] >= 1
    ChatStore._instance = None
