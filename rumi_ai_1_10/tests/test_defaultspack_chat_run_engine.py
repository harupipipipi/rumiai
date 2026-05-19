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


def test_prepare_chat_run_injects_matched_skill_and_chat_references(tmp_path, monkeypatch):
    import json

    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    extensions_root = tmp_path / "extensions"
    skill_dir = extensions_root / "skills" / "line-mention"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "feedback/line-mention",
                "category": "skill",
                "version": "1",
                "enabled": True,
                "display_name": "LINE mention skill",
                "description": "Only respond to LINE groups when mentioned.",
                "triggers": ["LINE", "mention"],
                "instructions": "For LINE group chats, respond only when Rumi is mentioned.",
            }
        ),
        encoding="utf-8",
    )
    unrelated_skill_dir = extensions_root / "skills" / "finance-only"
    unrelated_skill_dir.mkdir(parents=True)
    (unrelated_skill_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "feedback/finance-only",
                "category": "skill",
                "version": "1",
                "enabled": True,
                "display_name": "Finance only",
                "triggers": ["portfolio-rebalance"],
                "instructions": "This must not appear in unrelated LINE prompts.",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTENSION_ROOTS", str(extensions_root))
    ChatStore._instance = None

    store = ChatStore()
    reference = store.create_conversation(model="stub/default")
    store.update_conversation(reference["id"], {"title": "Reference planning chat"})
    store.add_message(reference["id"], {"role": "user", "content": "We decided the rollout should avoid marker-based tests."})
    store.add_message(reference["id"], {"role": "assistant", "content": "Use tool_logs and metadata as evidence instead."})
    conversation = store.create_conversation(model="stub/default")
    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {
                "role": "user",
                "content": "LINE mention behavior please",
                "metadata": {
                    "dropped_widgets": [
                        {
                            "id": "conversation:" + reference["id"],
                            "type": "conversation",
                            "label": "Reference planning chat",
                            "sourceItemId": reference["id"],
                            "metadata": {
                                "conversation_id": reference["id"],
                                "title": "Reference planning chat",
                            },
                        }
                    ]
                },
            },
            "tools": [],
        },
        {},
    )
    combined = "\n".join(str(message.get("content") or "") for message in prepared.standard_messages)

    assert "active system-level instructions" in combined
    assert "For LINE group chats" in combined
    assert "portfolio-rebalance" not in combined
    assert prepared.matched_skills[0]["id"] == "feedback/line-mention"
    assert prepared.chat_references["history_json_path"].endswith("history.json")
    assert prepared.chat_references["references"][0]["conversation_id"] == reference["id"]
    assert prepared.chat_references["references"][0]["title"] == "Reference planning chat"
    assert "avoid marker-based tests" in prepared.chat_references["references"][0]["summary"]
    assert "Dropped Chat References" in combined
    assert reference["id"] in combined
    assert prepared.request_context["chat_references"] == prepared.chat_references
    assert prepared.tool_context["history_json_path"] == prepared.chat_references["history_json_path"]
    stored_user = ChatStore().get_message(conversation["id"], prepared.user_message["id"])
    assert stored_user["metadata"]["chat_references"]["history_json_path"] == prepared.chat_references["history_json_path"]
    assert stored_user["metadata"]["chat_references"]["references"][0]["conversation_id"] == reference["id"]
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
        model_routing={},
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
