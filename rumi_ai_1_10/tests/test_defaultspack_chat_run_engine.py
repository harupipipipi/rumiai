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


def test_prepare_chat_run_allows_explicit_model_override(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="gitlawb-opengateway/mimo-v2-omni")

    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "scheduled reminder"},
            "params": {"model": "google/gemini-2.5-flash"},
            "tools": [],
        },
        {"run_source": "scheduler"},
    )

    assert prepared.model == "google/gemini-2.5-flash"
    assert prepared.request_context["model"] == "google/gemini-2.5-flash"
    ChatStore._instance = None


def test_prepare_chat_run_forwards_approval_followup_token_to_tool_context(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {
                "role": "user",
                "content": "ユーザーが許可しました。承認済みの操作を続行してください。",
                "metadata": {
                    "approval_followup": {
                        "approval_token": "tok_approved",
                        "operation": "tool.coding_file_create",
                        "request_id": "apr_1",
                        "tool_name": "coding_file_create",
                    },
                },
            },
            "tools": [],
        },
        {},
    )

    expected = {
        "coding_file_create": "tok_approved",
        "tool.coding_file_create": "tok_approved",
        "apr_1": "tok_approved",
    }
    assert prepared.request_context["tool_approval_tokens"] == expected
    assert prepared.tool_context["tool_approval_tokens"] == expected
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
    assert stored_user["metadata"]["dropped_widgets"][0]["sourceItemId"] == reference["id"]
    assert stored_user["metadata"]["chat_references"]["history_json_path"] == prepared.chat_references["history_json_path"]
    assert stored_user["metadata"]["chat_references"]["references"][0]["conversation_id"] == reference["id"]
    ChatStore._instance = None


def test_prepare_chat_run_leaves_unmatched_skills_out_of_system_context(tmp_path, monkeypatch):
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
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTENSION_ROOTS", str(extensions_root))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "Summarize the local project notes."},
            "tools": [],
        },
        {},
    )
    combined = "\n".join(str(message.get("content") or "") for message in prepared.standard_messages)

    assert prepared.matched_skills == []
    assert "For LINE group chats" not in combined
    assert "matched_skill_instructions" not in prepared.request_context
    assert "matched_skill_instructions" not in prepared.tool_context
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


def test_stream_empty_thinking_retry_preserves_tools_for_tool_calls():
    from domain.chat.run_request import PreparedChatRun
    from domain.chat.stream_engine import ChatRunEngine

    class GoogleProvider:
        pass

    class FakeGateway:
        def __init__(self):
            self.complete_requests = []

        def resolve_provider(self, model):
            return GoogleProvider(), model

        def supports_stream(self, model):
            return True

        def stream(self, request):
            yield {"type": "thinking_delta", "delta": {"type": "text", "text": "I should use a tool."}}
            yield {"type": "stream_end", "finish_reason": "stop", "usage": {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1}}

        def complete(self, request):
            self.complete_requests.append(request)
            return {
                "content": [
                    {"type": "text", "text": ""},
                    {
                        "type": "tool_use",
                        "id": "call-browser-1",
                        "name": "browser_computer",
                        "input": {"action": "computer.context", "payload": {}},
                    },
                ],
                "finish_reason": "tool_calls",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

    gateway = FakeGateway()
    engine = ChatRunEngine(store=object(), gateway=gateway)
    provider_tools = [
        {
            "type": "function",
            "function": {
                "name": "browser_computer",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    prepared = PreparedChatRun(
        conversation_id="conv-1",
        conversation={"id": "conv-1"},
        input_data={},
        request_id="req-1",
        content=[],
        metadata=None,
        user_message={"id": "user-1"},
        model="google/gemma-4-31b-it",
        params={"thinking_level": "high", "reasoning_effort": "high"},
        request_context={},
        tool_context={},
        standard_messages=[],
        user_text="computer use使ってみて",
        system_prompt="",
        enrich_info={},
        raw_tools=provider_tools,
        provider_tools=provider_tools,
        tools_called=["browser_computer"],
        connected_tool_names={"browser_computer"},
        call_handler=None,
        model_routing={},
    )

    generator = engine._model_turn(prepared, [{"role": "user", "content": "computer use使ってみて"}], None)
    events = []
    try:
        while True:
            events.append(next(generator))
    except StopIteration as exc:
        response, tool_uses = exc.value

    assert gateway.complete_requests
    assert gateway.complete_requests[0]["tools"] == provider_tools
    assert "thinking_level" not in gateway.complete_requests[0]["params"]
    assert "reasoning_effort" not in gateway.complete_requests[0]["params"]
    assert response["metadata"]["recovered_from_empty_stream"] is True
    assert response["metadata"]["fallback_kept_tools"] is True
    assert tool_uses[0]["name"] == "browser_computer"
    assert any(event.get("type") == "thinking_delta" for event in events)


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


class _IRFakeGateway:
    def __init__(self):
        self.complete_requests = []
        self.calls = 0

    def complete(self, request):
        self.complete_requests.append(request)
        self.calls += 1
        if self.calls == 1:
            return {
                "content": [{"type": "tool_use", "id": "call-ir-1", "name": "lookup", "input": {"q": "x"}}],
                "finish_reason": "tool_calls",
            }
        return {"content": [{"type": "text", "text": "done"}], "finish_reason": "stop", "usage": {}}

    def stream(self, request):
        return iter([])

    def supports_stream(self, model):
        return False

    def resolve_provider(self, model):
        class Provider:
            pass

        return Provider(), model.split("/", 1)[1] if "/" in model else model


def _run_ir_tool_loop(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine
    from domain.tool.executor import ToolExecutor

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="openai/gpt-5.4")
    monkeypatch.setattr(ToolExecutor, "execute", lambda self, name, arguments, context: {"result": "tool ok", "is_error": False})
    gateway = _IRFakeGateway()
    engine = ChatRunEngine(store=store, gateway=gateway)
    events = list(
        engine.stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "use tool"},
                "tools": [{"tool_id": "lookup", "name": "lookup", "summary": "lookup", "schema": {"parameters": {"type": "object"}}}],
            },
            {},
            stream_mode=False,
        )
    )
    stored = store.get_conversation(conversation["id"])["messages"][-1]
    return gateway, events, stored, store


def test_stream_engine_ir_tool_loop_matches_legacy(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    gateway, events, stored, store = _run_ir_tool_loop(tmp_path, monkeypatch)

    assert any(message.get("content") == "use tool" for message in gateway.complete_requests[0]["messages"])
    assert gateway.complete_requests[1]["messages"][-2]["tool_calls"][0]["id"] == "call-ir-1"
    assert stored["raw_text"] == "done"
    assert any(event.get("type") == "tool_call_completed" for event in events)
    ChatStore._instance = None


def test_stream_engine_ir_preserves_tool_call_ids(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    gateway, events, stored, store = _run_ir_tool_loop(tmp_path, monkeypatch)

    assert any(event.get("data", {}).get("tool_call_id") == "call-ir-1" for event in events)
    assert stored["tool_logs"][0]["tool_call_id"] == "call-ir-1"
    ChatStore._instance = None


def test_stream_engine_provider_trace_metadata(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from pathlib import Path

    gateway, events, stored, store = _run_ir_tool_loop(tmp_path, monkeypatch)

    trace = stored["metadata"]["provider_trace"]
    assert trace["request_id"]
    assert Path(trace["trace_path"]).exists()
    assert stored["metadata"]["ir"]["schema_version"] == "rumi.chat.ir.v2"
    assert "provider_planning" in stored["metadata"]
    planning = stored["metadata"]["provider_planning"]
    assert planning["provider_tool_count"] == 1
    assert planning["provider_tools"][0]["name"] == "lookup"
    assert "parameters" not in str(planning["provider_tools"][0])
    ChatStore._instance = None


def test_stream_engine_legacy_flag_uses_legacy_messages(monkeypatch):
    from domain.chat.stream_engine import ChatRunEngine
    from domain.chat.run_request import PreparedChatRun

    monkeypatch.setenv("RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2", "1")
    monkeypatch.setenv("RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES", "1")

    assert ChatRunEngine._use_provider_compiler(PreparedChatRun(conversation_id="c", conversation={}, input_data={}, request_id="r", content=[], metadata={}, user_message={}, model="m", params={}, request_context={}, tool_context={}, standard_messages=[], user_text="", system_prompt="", enrich_info={}, raw_tools=[], provider_tools=[], tools_called=[], connected_tool_names=set(), call_handler=None, model_routing={})) is False


def test_stream_engine_ir_handles_streaming_tool_delta():
    from domain.chat.stream_engine import ChatRunEngine
    from domain.chat.run_request import PreparedChatRun

    class Gateway:
        def supports_stream(self, model):
            return True

        def stream(self, request):
            return iter(
                [
                    {"type": "tool_call_start", "id": "tc", "name": "lookup"},
                    {"type": "tool_call_delta", "id": "tc", "name": "lookup", "arguments_chunk": "{\"q\""},
                    {"type": "tool_call_delta", "id": "tc", "name": "lookup", "arguments_chunk": ":\"x\"}"},
                    {"type": "tool_call_end", "id": "tc", "name": "lookup"},
                    {"type": "stream_end", "finish_reason": "tool_calls", "usage": {}},
                ]
            )

        def complete(self, request):
            raise AssertionError("complete should not be called")

        def resolve_provider(self, model):
            class OpenAIProvider:
                pass

            return OpenAIProvider(), model

    engine = ChatRunEngine(gateway=Gateway())
    prepared = PreparedChatRun(conversation_id="c", conversation={}, input_data={}, request_id="r", content=[], metadata={}, user_message={"id": "u"}, model="openai/gpt", params={}, request_context={}, tool_context={}, standard_messages=[], user_text="", system_prompt="", enrich_info={}, raw_tools=[], provider_tools=[{"type": "function", "function": {"name": "lookup"}}], tools_called=["lookup"], connected_tool_names={"lookup"}, call_handler=None, model_routing={})
    generator = engine._model_turn(prepared, [{"role": "user", "content": "hi"}], None)
    events = []
    try:
        while True:
            events.append(next(generator))
    except StopIteration as exc:
        response, tool_uses = exc.value

    assert tool_uses[0]["id"] == "tc"
    assert tool_uses[0]["input"] == {"q": "x"}
    assert any(event.get("type") == "tool_call_delta" for event in events)


def test_stream_engine_ir_finalizes_assistant_message(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    gateway, events, stored, store = _run_ir_tool_loop(tmp_path, monkeypatch)

    assert stored["role"] == "assistant"
    assert stored["finish_reason"] == "stop"
    assert stored["metadata"]["provider_capabilities"]["provider_id"] == "openai"
    ChatStore._instance = None
