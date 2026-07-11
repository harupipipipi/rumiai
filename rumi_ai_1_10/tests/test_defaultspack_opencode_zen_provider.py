from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _FakeSseResponse:
    def __init__(self, chunks):
        self._lines = iter(b"".join(chunks).splitlines(keepends=True))
        self.closed = False

    def readline(self):
        return next(self._lines, b"")

    def close(self):
        self.closed = True


def _provider(monkeypatch):
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    return OpencodeZenProvider()


def test_opencode_zen_catalog_includes_mimo_v2_5_free():
    from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map

    catalog = get_provider_catalog_map()
    provider = catalog["opencode-zen"]
    models = {item["id"]: item for item in get_all_known_models("opencode-zen")}

    assert provider["metadata"]["adapter"] == "python_entrypoint"
    assert provider["metadata"]["default_base_url"] == "https://opencode.ai/zen"
    assert provider["env_vars"] == ["OPENCODE_ZEN_API_KEY"]
    assert provider["metadata"]["default_base_url"] == "https://opencode.ai/zen"
    assert provider["default_model"] == "mimo-v2.5-free"
    assert provider["default_model_for"]["coding"] == "mimo-v2.5-free"
    assert "opencode-zen/mimo-v2.5-free" in models
    mimo = models["opencode-zen/mimo-v2.5-free"]
    assert mimo["model_id"] == "mimo-v2.5-free"
    assert mimo["metadata"]["transport"] == "openai_chat_completions"
    assert mimo["metadata"]["api_compatibility"] == "openai_chat_completions"
    assert mimo["metadata"]["endpoint_path"] == "/v1/chat/completions"
    assert not mimo["metadata"]["capabilities"]["tool_calling"]


def test_opencode_zen_complete_uses_openai_chat_completions(monkeypatch):
    provider = _provider(monkeypatch)
    captured = {}

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {
            "id": "msg_test",
            "model": "mimo-v2.5-free",
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        result = provider.complete(
            "opencode-zen/mimo-v2.5-free",
            [
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": "Say OK"},
            ],
            [{"name": "noop", "input_schema": {"type": "object"}}],
            {"max_tokens": 8, "temperature": 0},
        )

    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["model"] == "mimo-v2.5-free"
    assert captured["body"]["max_tokens"] == 8
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "Be terse."},
        {"role": "user", "content": "Say OK"},
    ]
    assert "tools" not in captured["body"]
    assert result["content"] == [{"type": "text", "text": "OK"}]


def test_opencode_zen_reasoning_only_response_is_normalized(monkeypatch):
    provider = _provider(monkeypatch)

    def fake_request_json(path, body):
        assert path == "/v1/chat/completions"
        assert body["model"] == "mimo-v2.5-free"
        return {
            "id": "chatcmpl_reasoning",
            "model": "mimo-v2.5-free",
            "choices": [
                {
                    "message": {"content": None, "reasoning_content": "thinking trace"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        result = provider.complete(
            "opencode/mimo-v2.5-free",
            [{"role": "user", "content": "Think only"}],
            [],
            {},
        )

    assert result["content"] == [{"type": "text", "text": ""}]
    assert result["metadata"]["reasoning_content"] == "thinking trace"
    assert result["usage"] == {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}


def test_opencode_zen_stream_uses_openai_sse_and_omits_tools(monkeypatch):
    provider = _provider(monkeypatch)
    captured = {}
    response = _FakeSseResponse(
        [
            b'data: {"choices":[{"delta":{"content":"O"},"finish_reason":null}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"K"},"finish_reason":null}]}\n\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}\n\n'
            b"data: [DONE]\n\n",
        ]
    )

    def fake_request_stream(path, body):
        captured["path"] = path
        captured["body"] = body
        return response

    with patch.object(provider, "_request_stream", side_effect=fake_request_stream):
        events = list(
            provider.stream(
                "opencode-zen/mimo-v2.5-free",
                [{"role": "user", "content": "Say OK"}],
                [{"name": "noop", "input_schema": {"type": "object"}}],
                {"max_tokens": 8},
            )
        )

    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["model"] == "mimo-v2.5-free"
    assert captured["body"]["max_tokens"] == 8
    assert "tools" not in captured["body"]
    assert events[0] == {"type": "content_delta", "delta": {"type": "text", "text": "O"}}
    assert events[1] == {"type": "content_delta", "delta": {"type": "text", "text": "K"}}
    assert events[-1]["type"] == "stream_end"
    assert events[-1]["usage"] == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
    assert response.closed is True


def test_opencode_zen_stream_finalizes_once_after_finish_usage_tail_and_done():
    """SSE terminal chunks must not create duplicate terminal events."""
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    # Bypass construction so this parser test never reads a credential or
    # creates a network-capable client.
    provider = object.__new__(OpencodeZenProvider)
    response = _FakeSseResponse(
        [
            b'data: {"choices":[{"delta":{"reasoning_content":"plan"},'
            b'"finish_reason":null}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"Answer"},'
            b'"finish_reason":"length"}],"usage":{"prompt_tokens":2,'
            b'"completion_tokens":3,"total_tokens":5}}\n\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
            b'data: {"choices":[],"usage":{"prompt_tokens":2,'
            b'"completion_tokens":4,"total_tokens":6}}\n\n'
            b'data: [DONE]\n\n',
        ]
    )

    events = list(provider._stream_from_response(response))

    assert [event["type"] for event in events] == [
        "reasoning_delta",
        "content_delta",
        "stream_end",
    ]
    assert events[0]["delta"] == {"type": "text", "text": "plan"}
    assert events[1]["delta"] == {"type": "text", "text": "Answer"}
    assert events[-1] == {
        "type": "stream_end",
        "finish_reason": "length",
        "usage": {"input_tokens": 2, "output_tokens": 4, "total_tokens": 6},
    }
    assert response.closed is True


def test_opencode_zen_stream_promotes_reasoning_only_mimo_response_to_content():
    """MiMo sometimes returns its complete answer only as reasoning_content."""
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    provider = object.__new__(OpencodeZenProvider)
    response = _FakeSseResponse(
        [
            b'data: {"choices":[{"delta":{"reasoning_content":"{\\"text\\":"},'
            b'"finish_reason":null}]}\n\n'
            b'data: {"choices":[{"delta":{"reasoning_content":"\\"ready\\"}"},'
            b'"finish_reason":null}]}\n\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\n'
            b'data: [DONE]\n\n',
        ]
    )

    events = list(provider._stream_from_response(response))

    assert [event["type"] for event in events] == [
        "reasoning_delta",
        "reasoning_delta",
        "content_delta",
        "stream_end",
    ]
    assert events[-2]["delta"] == {"type": "text", "text": '{"text":"ready"}'}
    assert events[-1]["finish_reason"] == "stop"


def test_opencode_zen_stream_does_not_promote_reasoning_when_content_exists():
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    provider = object.__new__(OpencodeZenProvider)
    response = _FakeSseResponse(
        [
            b'data: {"choices":[{"delta":{"reasoning_content":"plan"},'
            b'"finish_reason":null}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"answer"},'
            b'"finish_reason":"stop"}]}\n\n'
            b'data: [DONE]\n\n',
        ]
    )

    events = list(provider._stream_from_response(response))

    assert [event["type"] for event in events] == [
        "reasoning_delta",
        "content_delta",
        "stream_end",
    ]
    assert events[1]["delta"]["text"] == "answer"


def test_opencode_zen_stream_reads_each_sse_line_without_waiting_for_eof():
    """A live SSE connection must expose deltas before the socket closes."""
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    provider = object.__new__(OpencodeZenProvider)

    class OpenSseResponse:
        def __init__(self):
            self.lines = iter(
                [
                    b'data: {"choices":[{"delta":{"content":"ready"}}]}\n',
                    b"\n",
                ]
            )
            self.closed = False

        def readline(self):
            try:
                return next(self.lines)
            except StopIteration:
                raise AssertionError("parser waited for connection EOF")

        def read(self, _size):
            raise AssertionError("buffered read delays small live SSE frames")

        def close(self):
            self.closed = True

    response = OpenSseResponse()
    stream = provider._stream_from_response(response)

    assert next(stream) == {
        "type": "content_delta",
        "delta": {"type": "text", "text": "ready"},
    }
    stream.close()
    assert response.closed is True


def test_opencode_zen_secret_keys_and_detection(monkeypatch):
    from domain.ai_client.api_key_store import provider_secret_keys
    from domain.ai_client.providers import detect_available_providers
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    assert provider_secret_keys("opencode-zen") == ["OPENCODE_ZEN_API_KEY"]
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")
    assert isinstance(detect_available_providers()["opencode-zen"], OpencodeZenProvider)


def test_opencode_zen_rejects_unknown_model(monkeypatch):
    provider = _provider(monkeypatch)

    with pytest.raises(RuntimeError, match="unsupported model"):
        provider.complete("opencode-zen/not-a-real-model", [{"role": "user", "content": "hi"}], [], {})


def _live_enabled():
    return os.environ.get("RUMI_OPENCODE_ZEN_LIVE_TEST") == "1" and bool(os.environ.get("OPENCODE_ZEN_API_KEY"))


@pytest.mark.live
@pytest.mark.skipif(not _live_enabled(), reason="set RUMI_OPENCODE_ZEN_LIVE_TEST=1 and OPENCODE_ZEN_API_KEY")
def test_opencode_zen_live_mimo_v2_5_free_complete():
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    result = OpencodeZenProvider().complete(
        "mimo-v2.5-free",
        [{"role": "user", "content": "Reply with exactly: OK"}],
        [],
        {"max_tokens": 8},
    )
    assert result["content"]
