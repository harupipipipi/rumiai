from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


_SEAL_RE = re.compile(r"⟪RUMI_SEAL:v1:[^⟫]{1,512}⟫")


def _extract_seal(messages):
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        match = _SEAL_RE.search(content)
        if match:
            return match.group(0)
    raise AssertionError("run seal was not injected")


def _prepared_chat_run(**overrides):
    from domain.chat.run_request import PreparedChatRun

    base = {
        "conversation_id": "conv-1",
        "conversation": {"id": "conv-1"},
        "input_data": {},
        "request_id": "req-1",
        "content": [],
        "metadata": None,
        "user_message": {"id": "user-1"},
        "model": "openai/gpt-5.4",
        "params": {"seal_policy": {"enabled": True, "max_retries": 1}},
        "request_context": {},
        "tool_context": {},
        "standard_messages": [],
        "user_text": "hello",
        "system_prompt": "Be terse.",
        "enrich_info": {},
        "raw_tools": [],
        "provider_tools": [],
        "tools_called": [],
        "connected_tool_names": set(),
        "call_handler": None,
        "model_routing": {},
    }
    base.update(overrides)
    return PreparedChatRun(**base)


def _drain(generator):
    events = []
    try:
        while True:
            events.append(next(generator))
    except StopIteration as exc:
        return exc.value, events


def test_run_seal_service_only_accepts_final_suffix():
    from domain.ai_client.run_seal import RunSealService

    service = RunSealService("secret")
    seal = service.create(run_id="run_1", system_prompt="system")

    ok = service.verify_and_strip(text="answer\n" + seal.marker, seal=seal)
    missing = service.verify_and_strip(text="answer only", seal=seal)
    interior = service.verify_and_strip(text="body " + seal.marker + "\nanswer", seal=seal)

    assert ok.ok is True
    assert ok.visible_text == "answer"
    assert missing.ok is False
    assert missing.reason == "missing_final_seal"
    assert interior.ok is False
    assert interior.visible_text == "body \nanswer"


def test_run_seal_service_sanitizes_leaked_marker_in_visible_text():
    from domain.ai_client.run_seal import RunSealService

    service = RunSealService("secret")
    seal = service.create(run_id="run_1", system_prompt="system")
    text = "preface " + seal.marker + "\nfinal answer\n" + seal.marker

    result = service.verify_and_strip(text=text, seal=seal)

    assert result.ok is True
    assert result.visible_text == "preface \nfinal answer"
    assert result.had_interior_seal is True


def test_run_seal_service_strips_inline_reasoning_tags_from_visible_text():
    from domain.ai_client.run_seal import RunSealService

    service = RunSealService("secret")
    seal = service.create(run_id="run_1", system_prompt="system")

    result = service.verify_and_strip(text="<think>private plan</think>OK\n" + seal.marker, seal=seal)

    assert result.ok is True
    assert result.visible_text == "OK"
    assert result.thinking_transcript == "private plan"


def test_chat_run_engine_run_seal_strips_suffix_and_records_metadata():
    from domain.chat.stream_engine import ChatRunEngine

    class Gateway:
        def __init__(self):
            self.requests = []

        def complete(self, request):
            self.requests.append(request)
            seal = _extract_seal(request["messages"])
            return {
                "content": [{"type": "text", "text": "sealed reply\n" + seal}],
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                "metadata": {},
            }

    engine = ChatRunEngine(store=object(), gateway=Gateway())
    engine._run_id = "run-seal-1"
    prepared = _prepared_chat_run()

    (response, tool_uses), events = _drain(
        engine._model_turn(
            prepared,
            [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "hello"}],
            None,
        )
    )

    assert tool_uses == []
    assert response["content"] == [{"type": "text", "text": "sealed reply"}]
    assert response["metadata"]["run_seal"]["ok"] is True
    assert response["metadata"]["run_seal"]["attempts"] == 1
    assert [event["type"] for event in events] == ["content_delta"]


def test_chat_run_engine_run_seal_hides_inline_reasoning_tags():
    from domain.chat.stream_engine import ChatRunEngine

    class Gateway:
        def complete(self, request):
            seal = _extract_seal(request["messages"])
            return {
                "content": [{"type": "text", "text": "<think>private chain</think>OK\n" + seal}],
                "finish_reason": "stop",
                "metadata": {},
            }

    engine = ChatRunEngine(store=object(), gateway=Gateway())
    engine._run_id = "run-seal-think"
    prepared = _prepared_chat_run()

    (response, tool_uses), events = _drain(
        engine._model_turn(
            prepared,
            [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "hello"}],
            None,
        )
    )

    assert tool_uses == []
    assert response["content"] == [{"type": "text", "text": "OK"}]
    assert response["metadata"]["thinking"]["transcript"] == "private chain"
    assert response["metadata"]["run_seal"]["had_inline_reasoning"] is True
    assert [event["type"] for event in events] == ["content_delta"]


def test_chat_run_engine_run_seal_retries_missing_suffix():
    from domain.chat.stream_engine import ChatRunEngine

    class Gateway:
        def __init__(self):
            self.requests = []

        def complete(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                return {
                    "content": [{"type": "text", "text": "first try"}],
                    "finish_reason": "stop",
                    "metadata": {},
                }
            seal = _extract_seal(request["messages"])
            return {
                "content": [{"type": "text", "text": "second try\n" + seal}],
                "finish_reason": "stop",
                "metadata": {},
            }

    engine = ChatRunEngine(store=object(), gateway=Gateway())
    engine._run_id = "run-seal-2"
    prepared = _prepared_chat_run()

    (response, tool_uses), events = _drain(
        engine._model_turn(
            prepared,
            [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "hello"}],
            None,
        )
    )

    assert tool_uses == []
    assert response["content"] == [{"type": "text", "text": "second try"}]
    assert response["metadata"]["run_seal"]["attempts"] == 2
    assert any(event.get("phase") == "run_seal_retry" for event in events)


def test_chat_run_engine_run_seal_compacts_after_length_finish():
    from domain.chat.stream_engine import ChatRunEngine

    class Gateway:
        def __init__(self):
            self.requests = []

        def complete(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                return {
                    "content": [{"type": "text", "text": "too long"}],
                    "finish_reason": "length",
                    "metadata": {},
                }
            seal = _extract_seal(request["messages"])
            return {
                "content": [{"type": "text", "text": "after compact\n" + seal}],
                "finish_reason": "stop",
                "metadata": {},
            }

    engine = ChatRunEngine(store=object(), gateway=Gateway())
    compact_calls = []
    engine._compact_messages_for_run_seal = lambda prepared, messages: compact_calls.append(list(messages)) or list(messages)
    prepared = _prepared_chat_run()

    (response, tool_uses), events = _drain(
        engine._model_turn(
            prepared,
            [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "hello"}],
            None,
        )
    )

    assert tool_uses == []
    assert response["content"] == [{"type": "text", "text": "after compact"}]
    assert len(compact_calls) == 1
    assert any(event.get("phase") == "run_seal_compact" for event in events)


def test_chat_run_engine_run_seal_skips_tool_use_turn():
    from domain.chat.stream_engine import ChatRunEngine

    class Gateway:
        def complete(self, request):
            return {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "lookup",
                        "input": {"q": "hello"},
                    }
                ],
                "finish_reason": "tool_calls",
                "metadata": {},
            }

    engine = ChatRunEngine(store=object(), gateway=Gateway())
    prepared = _prepared_chat_run(
        provider_tools=[{"type": "function", "function": {"name": "lookup"}}],
        raw_tools=[{"type": "function", "function": {"name": "lookup"}}],
        tools_called=["lookup"],
        connected_tool_names={"lookup"},
    )

    (response, tool_uses), events = _drain(
        engine._model_turn(
            prepared,
            [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "hello"}],
            None,
        )
    )

    assert response["finish_reason"] == "tool_calls"
    assert tool_uses[0]["name"] == "lookup"
    assert events == []
