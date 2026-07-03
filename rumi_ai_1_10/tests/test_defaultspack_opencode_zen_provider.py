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
        self._chunks = iter(chunks)
        self.closed = False

    def read(self, size):
        del size
        return next(self._chunks, b"")

    def close(self):
        self.closed = True


def _provider(monkeypatch):
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    return OpencodeZenProvider()


def test_opencode_zen_catalog_includes_curated_free_models():
    from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map

    catalog = get_provider_catalog_map()
    provider = catalog["opencode-zen"]
    models = {item["id"]: item for item in get_all_known_models("opencode-zen")}

    assert provider["metadata"]["adapter"] == "python_entrypoint"
    assert provider["metadata"]["default_base_url"] == "https://opencode.ai/zen"
    assert provider["env_vars"] == ["OPENCODE_ZEN_API_KEY"]
    assert provider["default_model_for"]["coding"] == "minimax-m3-free"
    assert provider["default_model_for"]["cheap"] == "mimo-v2.5-free"
    assert "opencode-zen/minimax-m3-free" in models
    assert models["opencode-zen/minimax-m3-free"]["metadata"]["transport"] == "anthropic_messages"
    assert models["opencode-zen/minimax-m3-free"]["metadata"]["endpoint_path"] == "/v1/messages"
    assert not models["opencode-zen/minimax-m3-free"]["metadata"]["capabilities"]["tool_calls"]
    assert models["opencode-zen/minimax-m3-free"]["metadata"]["min_output_tokens"] == 96
    assert "opencode-zen/mimo-v2.5-free" in models
    mimo = models["opencode-zen/mimo-v2.5-free"]
    assert mimo["metadata"]["transport"] == "openai_chat_completions"
    assert mimo["metadata"]["endpoint_path"] == "/v1/chat/completions"
    assert mimo["metadata"]["free_tier"] is True
    assert mimo["metadata"]["capabilities"]["tool_calls"] is False
    assert mimo["metadata"]["capabilities"]["reasoning"] is False
    assert "tool_calls_verified" not in mimo["metadata"]
    assert "reasoning_effort_verified" not in mimo["metadata"]


def test_opencode_zen_complete_uses_anthropic_messages(monkeypatch):
    provider = _provider(monkeypatch)
    captured = {}

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {
            "id": "msg_test",
            "model": "minimax-m3-free",
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        result = provider.complete(
            "opencode/minimax-m3-free",
            [
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": "Say OK"},
            ],
            [{"name": "noop", "input_schema": {"type": "object"}}],
            {"max_tokens": 8, "temperature": 0},
        )

    assert captured["path"] == "/v1/messages"
    assert captured["body"]["model"] == "minimax-m3-free"
    assert captured["body"]["max_tokens"] == 96
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["system"] == [{"type": "text", "text": "Be terse."}]
    assert "tools" not in captured["body"]
    assert result["content"] == [{"type": "text", "text": "OK"}]


def test_opencode_zen_mimo_free_uses_openai_chat_completions(monkeypatch):
    provider = _provider(monkeypatch)
    captured = {}

    def fake_request_openai_json(path, body, **kwargs):
        del kwargs
        captured["path"] = path
        captured["body"] = body
        return {
            "id": "chatcmpl_test",
            "model": "mimo-v2.5-free",
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    with patch.object(provider, "_request_openai_json", side_effect=fake_request_openai_json):
        result = provider.complete(
            "opencode-zen/mimo-v2.5-free",
            [{"role": "user", "content": "Say OK"}],
            [{"type": "function", "function": {"name": "noop"}}],
            {
                "max_tokens": 8,
                "temperature": 0,
                "reasoning_effort": "high",
                "tool_choice": "auto",
            },
        )

    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["model"] == "mimo-v2.5-free"
    assert captured["body"]["max_tokens"] == 8
    assert captured["body"]["temperature"] == 0
    assert "tools" not in captured["body"]
    assert "tool_choice" not in captured["body"]
    assert "reasoning_effort" not in captured["body"]
    assert result["content"] == [{"type": "text", "text": "OK"}]


def test_opencode_zen_mimo_free_preserves_tool_call_continuations(monkeypatch):
    provider = _provider(monkeypatch)
    captured = {}

    def fake_request_openai_json(path, body, **kwargs):
        del kwargs
        captured["path"] = path
        captured["body"] = body
        return {
            "id": "chatcmpl_tool_followup",
            "model": "mimo-v2.5-free",
            "choices": [{"message": {"content": "Done"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
        }

    messages = [
        {"role": "user", "content": "Call noop."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_noop",
                    "type": "function",
                    "function": {"name": "noop", "arguments": "{}"},
                }
            ],
            "metadata": {"thinking": {"transcript": "Need the noop result."}},
        },
        {"role": "tool", "tool_call_id": "call_noop", "name": "noop", "content": {"ok": True}},
    ]

    with patch.object(provider, "_request_openai_json", side_effect=fake_request_openai_json):
        result = provider.complete("opencode-zen/mimo-v2.5-free", messages, [], {"max_tokens": 8})

    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["messages"][1]["tool_calls"] == messages[1]["tool_calls"]
    assert captured["body"]["messages"][1]["reasoning_content"] == "Need the noop result."
    assert captured["body"]["messages"][2] == {
        "role": "tool",
        "tool_call_id": "call_noop",
        "name": "noop",
        "content": '{"ok": true}',
    }
    assert result["content"] == [{"type": "text", "text": "Done"}]


def test_opencode_zen_stream_omits_tools_and_applies_token_floor(monkeypatch):
    provider = _provider(monkeypatch)
    captured = {}
    response = _FakeSseResponse(
        [
            b'event: message_start\ndata: {"message":{"usage":{"input_tokens":1}}}\n\n'
            b'event: content_block_delta\ndata: {"delta":{"type":"text_delta","text":"OK"}}\n\n'
            b'event: message_delta\ndata: {"delta":{"stop_reason":"end_turn"},'
            b'"usage":{"output_tokens":1}}\n\n'
            b"event: message_stop\ndata: {}\n\n",
        ]
    )

    def fake_request_stream(path, body):
        captured["path"] = path
        captured["body"] = body
        return response

    with patch.object(provider, "_request_stream", side_effect=fake_request_stream):
        events = list(
            provider.stream(
                "opencode-zen/minimax-m3-free",
                [{"role": "user", "content": "Say OK"}],
                [{"name": "noop", "input_schema": {"type": "object"}}],
                {"max_tokens": 8},
            )
        )

    assert captured["path"] == "/v1/messages"
    assert captured["body"]["model"] == "minimax-m3-free"
    assert captured["body"]["max_tokens"] == 96
    assert "tools" not in captured["body"]
    assert events[0] == {"type": "content_delta", "delta": {"type": "text", "text": "OK"}}
    assert events[-1]["type"] == "stream_end"
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
def test_opencode_zen_live_minimax_m3_free_complete():
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    result = OpencodeZenProvider().complete(
        "minimax-m3-free",
        [{"role": "user", "content": "Reply with exactly: OK"}],
        [],
        {"max_tokens": 8},
    )
    assert result["content"]
