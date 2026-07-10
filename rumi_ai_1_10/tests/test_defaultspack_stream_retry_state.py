from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class ScriptedGateway:
    """Serve deterministic provider stream attempts for retry tests."""

    def __init__(self, scripts: list[list[dict[str, Any] | BaseException]]) -> None:
        self.scripts = scripts
        self.calls = 0

    def supports_stream(self, model: str) -> bool:
        del model
        return True

    def resolve_provider(self, model: str) -> tuple[object, str]:
        class OpenAIProvider:
            pass

        return OpenAIProvider(), model

    def stream(self, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
        del request
        script = self.scripts[self.calls]
        self.calls += 1
        for item in script:
            if isinstance(item, BaseException):
                raise item
            yield item

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        del request
        raise AssertionError("complete fallback should not run")


def prepared_run(*, retry_delay: float = 0) -> Any:
    """Build the minimum prepared run required by the stream engine."""
    from domain.chat.run_request import PreparedChatRun

    provider_tools = [
        {
            "type": "function",
            "function": {
                "name": "coding_file_read",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    return PreparedChatRun(
        conversation_id="conv-stream-retry",
        conversation={"id": "conv-stream-retry"},
        input_data={},
        request_id="req-stream-retry",
        content=[],
        metadata=None,
        user_message={"id": "user-stream-retry"},
        model="openai/gpt-test",
        params={"retry": {"max_attempts": 2, "delays": [retry_delay]}},
        request_context={},
        tool_context={},
        standard_messages=[],
        user_text="read README",
        system_prompt="",
        enrich_info={},
        raw_tools=provider_tools,
        provider_tools=provider_tools,
        tools_called=["coding_file_read"],
        connected_tool_names={"coding_file_read"},
        call_handler=None,
        model_routing={},
    )


def drain_model_turn(generator: Iterator[Any]) -> tuple[list[dict[str, Any]], Any]:
    """Collect yielded events and return a generator's final value."""
    events: list[dict[str, Any]] = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as exc:
            return events, exc.value


@pytest.mark.parametrize("failed_call_id", ["call-1", "failed-call"])
def test_retry_isolates_partial_tool_arguments_between_attempts(
    failed_call_id: str,
) -> None:
    from domain.chat.stream_engine import ChatRunEngine

    gateway = ScriptedGateway(
        [
            [
                {
                    "type": "tool_call_start",
                    "id": failed_call_id,
                    "name": "coding_file_read",
                },
                {
                    "type": "tool_call_delta",
                    "id": failed_call_id,
                    "name": "coding_file_read",
                    "arguments_chunk": '{"path":',
                },
                RuntimeError("503 temporary"),
            ],
            [
                {
                    "type": "tool_call_start",
                    "id": "call-1",
                    "name": "coding_file_read",
                },
                {
                    "type": "tool_call_delta",
                    "id": "call-1",
                    "name": "coding_file_read",
                    "arguments_chunk": '{"path":"README.md"}',
                },
                {
                    "type": "tool_call_end",
                    "id": "call-1",
                    "name": "coding_file_read",
                },
                {"type": "stream_end", "finish_reason": "tool_calls"},
            ],
        ]
    )
    engine = ChatRunEngine(gateway=gateway)

    events, (_response, tool_uses) = drain_model_turn(
        engine._model_turn(
            prepared_run(),
            [{"role": "user", "content": "read README"}],
            None,
        )
    )

    assert gateway.calls == 2
    assert tool_uses == [
        {
            "type": "tool_use",
            "id": "call-1",
            "name": "coding_file_read",
            "input": {"path": "README.md"},
        }
    ]
    assert any(event.get("type") == "ai_retry_scheduled" for event in events)
    discarded = [
        event for event in events if event.get("data", {}).get("provider_attempt_discarded") is True
    ]
    assert [event["data"]["tool_call_id"] for event in discarded] == [failed_call_id]


def test_tool_call_accumulator_drops_incomplete_or_malformed_calls() -> None:
    from domain.chat.tool_call_accumulator import ToolCallAccumulator

    accumulator = ToolCallAccumulator()
    accumulator.ingest({"type": "tool_call_start", "id": "incomplete", "name": "coding_file_read"})
    accumulator.ingest(
        {
            "type": "tool_call_delta",
            "id": "incomplete",
            "arguments_chunk": '{"path":',
        }
    )
    accumulator.ingest({"type": "tool_call_start", "id": "malformed", "name": "coding_file_read"})
    accumulator.ingest(
        {
            "type": "tool_call_delta",
            "id": "malformed",
            "arguments_chunk": "not-json",
        }
    )
    accumulator.ingest({"type": "tool_call_end", "id": "malformed", "name": "coding_file_read"})
    accumulator.ingest({"type": "tool_call_start", "id": "valid", "name": "coding_file_read"})
    accumulator.ingest(
        {
            "type": "tool_call_delta",
            "id": "valid",
            "arguments_chunk": '{"path":"README.md"}',
        }
    )
    accumulator.ingest({"type": "tool_call_end", "id": "valid", "name": "coding_file_read"})

    assert accumulator.tool_uses() == [
        {
            "type": "tool_use",
            "id": "valid",
            "name": "coding_file_read",
            "input": {"path": "README.md"},
        }
    ]


@pytest.mark.parametrize(
    "arguments_chunk",
    ['{"path":', '"README.md"', '["README.md"]', "not-json"],
)
def test_stream_never_executes_incomplete_or_non_object_tool_arguments(
    arguments_chunk: str,
) -> None:
    from domain.chat.stream_engine import ChatRunEngine

    gateway = ScriptedGateway(
        [
            [
                {
                    "type": "tool_call_start",
                    "id": "unsafe-call",
                    "name": "coding_file_read",
                },
                {
                    "type": "tool_call_delta",
                    "id": "unsafe-call",
                    "name": "coding_file_read",
                    "arguments_chunk": arguments_chunk,
                },
                {
                    "type": "tool_call_end",
                    "id": "unsafe-call",
                    "name": "coding_file_read",
                },
                {"type": "content_delta", "delta": {"text": "safe fallback"}},
                {"type": "stream_end", "finish_reason": "stop"},
            ]
        ]
    )
    engine = ChatRunEngine(gateway=gateway)

    _events, (response, tool_uses) = drain_model_turn(
        engine._model_turn(
            prepared_run(),
            [{"role": "user", "content": "read README"}],
            None,
        )
    )

    assert response["content"] == [{"type": "text", "text": "safe fallback"}]
    assert tool_uses == []


def test_retry_discards_thinking_from_failed_attempt() -> None:
    from domain.chat.stream_engine import ChatRunEngine

    gateway = ScriptedGateway(
        [
            [
                {"type": "thinking_delta", "delta": {"text": "discarded thought"}},
                RuntimeError("503 temporary"),
            ],
            [
                {"type": "content_delta", "delta": {"text": "success"}},
                {"type": "stream_end", "finish_reason": "stop"},
            ],
        ]
    )
    engine = ChatRunEngine(gateway=gateway)

    _events, (response, tool_uses) = drain_model_turn(
        engine._model_turn(prepared_run(), [{"role": "user", "content": "hi"}], None)
    )

    assert response["content"] == [{"type": "text", "text": "success"}]
    assert tool_uses == []
    assert "discarded thought" not in "".join(engine._thinking_transcript_parts)


def test_retry_discards_usage_from_failed_attempt() -> None:
    from domain.chat.stream_engine import ChatRunEngine

    gateway = ScriptedGateway(
        [
            [
                {
                    "type": "stream_end",
                    "finish_reason": "length",
                    "usage": {
                        "input_tokens": 999,
                        "output_tokens": 999,
                        "total_tokens": 1998,
                    },
                },
                RuntimeError("503 temporary"),
            ],
            [
                {"type": "content_delta", "delta": {"text": "success"}},
                {
                    "type": "stream_end",
                    "finish_reason": "stop",
                    "usage": {
                        "input_tokens": 3,
                        "output_tokens": 1,
                        "total_tokens": 4,
                    },
                },
            ],
        ]
    )
    engine = ChatRunEngine(gateway=gateway)

    _events, (response, tool_uses) = drain_model_turn(
        engine._model_turn(prepared_run(), [{"role": "user", "content": "hi"}], None)
    )

    assert response["finish_reason"] == "stop"
    assert response["usage"] == {
        "input_tokens": 3,
        "output_tokens": 1,
        "total_tokens": 4,
    }
    assert tool_uses == []


def test_partial_text_after_tool_result_wins_over_generic_error() -> None:
    from domain.chat.stream_engine import ChatRunEngine

    gateway = ScriptedGateway(
        [
            [
                {"type": "content_delta", "delta": {"text": "partial summary"}},
                RuntimeError("503 after tool result"),
            ]
        ]
    )
    engine = ChatRunEngine(gateway=gateway)
    engine._tool_logs = [{"tool_name": "coding_file_read", "result": {"status": "ok"}}]

    _events, (response, tool_uses) = drain_model_turn(
        engine._model_turn(prepared_run(), [{"role": "user", "content": "hi"}], None)
    )

    assert response["content"] == [{"type": "text", "text": "partial summary"}]
    assert response["finish_reason"] == "error"
    assert response["metadata"]["interrupted"] is True
    assert tool_uses == []


@pytest.mark.parametrize(
    "provider_error",
    [RuntimeError("503 temporary disconnect"), ValueError("invalid provider frame")],
)
def test_provider_failure_persists_visible_partial_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_error: BaseException,
) -> None:
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    class PartialClient:
        def __init__(self) -> None:
            self.calls = 0

        def supports_stream(self, model: str) -> bool:
            del model
            return True

        def stream(
            self,
            model: str,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            params: dict[str, Any] | None = None,
        ) -> Iterator[dict[str, Any]]:
            del model, messages, tools, params
            self.calls += 1
            yield {
                "type": "content_delta",
                "delta": {"type": "text", "text": "valuable partial answer"},
            }
            raise provider_error

        def complete(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            del args, kwargs
            raise AssertionError("visible partial output must not be retried")

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    client = PartialClient()
    events = list(
        ChatRunEngine(client=client).stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "answer this"},
                "tools": [],
                "params": {"retry": {"max_attempts": 2, "delays": [0]}},
            },
            {},
            stream_mode=True,
        )
    )

    assert client.calls == 1
    assert any(event.get("type") == "task_failed" for event in events)
    final = [event["data"]["message"] for event in events if event["type"] == "done"][-1]
    assert final["raw_text"] == "valuable partial answer"
    assert final["finish_reason"] == "error"
    assert final["metadata"]["interrupted"] is True
    assert final["metadata"]["interruption_reason"] == "provider_stream_error"
    assert final["metadata"]["provider_error"]["raw_message"] == str(provider_error)

    ChatStore._instance = None
    reloaded = ChatStore().get_conversation(conversation["id"])
    assert reloaded["messages"][-1]["raw_text"] == "valuable partial answer"
    assert reloaded["messages"][-1]["metadata"]["interrupted"] is True
    ChatStore._instance = None


def test_partial_response_metadata_redacts_raw_provider_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine

    secret = "sk-" + ("1" * 30)
    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    gateway = ScriptedGateway(
        [
            [
                {"type": "content_delta", "delta": {"text": "partial"}},
                RuntimeError(f"503 temporary api_key={secret}"),
            ]
        ]
    )
    store = ChatStore()
    conversation = store.create_conversation(model="openai/gpt-test")
    events = list(
        ChatRunEngine(store=store, gateway=gateway).stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "answer this"},
                "tools": [],
                "params": {"retry": {"max_attempts": 2, "delays": [0]}},
            },
            {},
            stream_mode=True,
        )
    )

    final = [event["data"]["message"] for event in events if event["type"] == "done"][-1]
    raw_message = final["metadata"]["provider_error"]["raw_message"]
    task_failed = [event for event in events if event["type"] == "task_failed"][-1]
    assert secret not in raw_message
    assert secret not in str(task_failed)
    assert "[redacted]" in raw_message

    ChatStore._instance = None


def test_retry_activity_redacts_raw_provider_secrets() -> None:
    from domain.chat.stream_engine import ChatRunEngine

    secret = "gho_" + ("1" * 30)
    gateway = ScriptedGateway(
        [
            [RuntimeError(f"503 temporary authorization=Bearer {secret}")],
            [
                {"type": "content_delta", "delta": {"text": "success"}},
                {"type": "stream_end", "finish_reason": "stop"},
            ],
        ]
    )
    engine = ChatRunEngine(gateway=gateway)

    events, (response, tool_uses) = drain_model_turn(
        engine._model_turn(prepared_run(), [{"role": "user", "content": "hi"}], None)
    )

    retry_event = [event for event in events if event["type"] == "ai_retry_scheduled"][-1]
    assert response["content"] == [{"type": "text", "text": "success"}]
    assert tool_uses == []
    assert secret not in str(retry_event)
    assert "[redacted]" in str(retry_event)


def test_stream_retry_backoff_remains_cancellable() -> None:
    from domain.chat.stream_engine import ChatRunEngine, _ChatCancelled

    gateway = ScriptedGateway(
        [[RuntimeError("503 temporary")], [{"type": "stream_end", "finish_reason": "stop"}]]
    )
    engine = ChatRunEngine(gateway=gateway)
    cancel_checks = 0

    def cancelled_during_backoff() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks >= 3

    engine._external_cancel_checker = cancelled_during_backoff
    generator = engine._model_turn(
        prepared_run(retry_delay=1),
        [{"role": "user", "content": "hi"}],
        None,
    )

    retry_event = next(generator)
    assert retry_event["type"] == "ai_retry_scheduled"
    with pytest.raises(_ChatCancelled):
        next(generator)
    assert gateway.calls == 1
