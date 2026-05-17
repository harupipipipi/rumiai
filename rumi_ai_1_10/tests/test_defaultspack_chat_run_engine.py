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


def test_prepare_chat_run_current_turn_history_mode_excludes_old_tool_logs(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    old_user = store.add_message(conversation["id"], {"role": "user", "content": "old external request"})
    store.add_message(
        conversation["id"],
        {
            "role": "assistant",
            "parent_id": old_user["id"],
            "content": [{"type": "text", "text": "old failed reply"}],
            "tool_logs": [{"tool_name": "browser_computer", "result": {"large": "x" * 5000}}],
        },
    )

    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "fresh external request"},
            "tools": [],
        },
        {"external_chat_history_mode": "current_turn"},
    )
    combined = "\n".join(str(message.get("content") or "") for message in prepared.standard_messages)

    assert "fresh external request" in combined
    assert "old external request" not in combined
    assert "old failed reply" not in combined
    ChatStore._instance = None


def test_complete_turn_retries_transient_ai_error_after_tool_use():
    from domain.chat.run_request import PreparedChatRun
    from domain.chat.stream_engine import ChatRunEngine

    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def complete(self, model, messages, tools=None, params=None):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Google API error 500: Internal error encountered.")
            return {
                "content": [{"type": "text", "text": "continued"}],
                "finish_reason": "stop",
            }

    client = FlakyClient()
    engine = ChatRunEngine(store=object(), client=client)
    engine._tool_logs = [{"tool_name": "browser_computer", "result": {"status": "ok"}}]
    prepared = PreparedChatRun(
        conversation_id="conv-1",
        conversation={"id": "conv-1"},
        input_data={},
        request_id="req-1",
        content=[],
        metadata=None,
        user_message={"id": "user-1"},
        model="google/gemma-4-31b-it",
        params={"retry": {"max_attempts": 2, "delays": [0]}},
        request_context={},
        tool_context={},
        standard_messages=[],
        user_text="hello",
        system_prompt="",
        enrich_info={},
        raw_tools=[],
        provider_tools=[],
        tools_called=[],
        connected_tool_names=set(),
        call_handler=None,
    )

    response = engine._complete_turn(prepared, [{"role": "user", "content": "hello"}])

    assert client.calls == 2
    assert response["content"] == [{"type": "text", "text": "continued"}]
    assert any(event.get("type") == "ai_retry_scheduled" for event in engine._activity_events)


def test_legacy_complete_with_tools_retries_transient_ai_error_after_tool_use():
    from blocks.chat import send

    ai_calls = 0
    tool_calls = 0

    def call_handler(name, payload):
        nonlocal ai_calls, tool_calls
        if name == "defaults.ai.complete":
            ai_calls += 1
            if ai_calls == 1:
                return {
                    "status": "ok",
                    "data": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call-1",
                                "name": "browser_computer",
                                "input": {"action": "computer.context", "payload": {}},
                            }
                        ],
                        "finish_reason": "tool_use",
                    },
                }
            if ai_calls == 2:
                return {
                    "status": "error",
                    "error": {"message": "Google API error 500: Internal error encountered."},
                }
            return {
                "status": "ok",
                "data": {
                    "content": [{"type": "text", "text": "continued after retry"}],
                    "finish_reason": "stop",
                },
            }
        if name == "defaults.tool.invoke":
            tool_calls += 1
            return {
                "status": "ok",
                "data": {"result": "ok", "is_error": False, "widget": None},
            }
        raise AssertionError(name)

    response = send._complete_with_tools(
        "google/gemma-4-31b-it",
        [{"role": "user", "content": "hello"}],
        [{"name": "browser_computer"}],
        {"profile_policy": {"max_tool_calls": 3}},
        call_handler,
        {"retry": {"max_attempts": 2, "delays": [0]}},
    )

    assert ai_calls == 3
    assert tool_calls == 1
    assert response["content"] == [{"type": "text", "text": "continued after retry"}]
    assert any(event.get("type") == "ai_retry_scheduled" for event in response["events"])
