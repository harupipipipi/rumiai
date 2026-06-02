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


ALL_MODELS = [
    "glm-5.1",
    "glm-5",
    "kimi-k2.6",
    "kimi-k2.5",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "qwen3.6-plus",
    "qwen3.5-plus",
    "minimax-m2.7",
    "minimax-m2.5",
    "mimo-v2-pro",
    "mimo-v2-omni",
    "hy3-preview",
]

OPENAI_CHAT_MODELS = [
    "glm-5.1",
    "glm-5",
    "kimi-k2.6",
    "kimi-k2.5",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "qwen3.6-plus",
    "qwen3.5-plus",
    "mimo-v2-pro",
    "mimo-v2-omni",
    "hy3-preview",
]

ANTHROPIC_MESSAGES_MODELS = ["minimax-m2.7", "minimax-m2.5"]


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
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "test-opencode-go-key")
    from domain.ai_client.providers.opencode_go_provider import OpencodeGoProvider

    return OpencodeGoProvider()


def test_opencode_go_catalog_includes_all_models():
    from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map

    catalog = get_provider_catalog_map()
    provider = catalog["opencode-go"]
    models = {item["id"]: item for item in get_all_known_models("opencode-go")}

    assert provider["metadata"]["adapter"] == "python_entrypoint"
    assert provider["metadata"]["default_base_url"] == "https://opencode.ai/zen/go/v1"
    assert provider["env_vars"] == ["OPENCODE_GO_API_KEY", "OPENCODE_ZEN_API_KEY"]
    assert provider["default_model_for"]["coding"] == "kimi-k2.6"
    assert provider["default_model_for"]["fast"] == "deepseek-v4-flash"
    assert provider["default_model_for"]["vision"] == "mimo-v2-omni"
    assert "vision" in provider["capabilities"]
    assert {f"opencode-go/{model}" for model in ALL_MODELS}.issubset(models)

    minimax = models["opencode-go/minimax-m2.7"]
    assert minimax["metadata"]["transport"] == "anthropic_messages"
    assert minimax["metadata"]["endpoint_path"] == "/messages"

    experimental = models["opencode-go/mimo-v2-omni"]
    assert experimental["defaults"]["vision"] is True
    assert "vision" in experimental["capabilities"]
    assert experimental["metadata"]["capabilities"]["vision"] is True
    assert experimental["metadata"]["transport"] == "openai_chat_completions"
    assert experimental["metadata"]["experimental"] is True
    assert experimental["metadata"]["vision_unverified"] is True

    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_model_catalog

    legacy_models = {item["id"]: item for item in list_model_catalog("opencode-go")}
    legacy_omni = legacy_models["opencode-go/mimo-v2-omni"]
    assert legacy_omni["supports_vision"] is True
    assert legacy_omni["supports_image_input"] is True


@pytest.mark.parametrize("model", OPENAI_CHAT_MODELS)
def test_opencode_go_uses_chat_completions_for_openai_compatible_models(monkeypatch, model):
    provider = _provider(monkeypatch)
    captured = {}

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {
            "id": "chatcmpl_test",
            "model": model,
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        result = provider.complete(
            f"opencode-go/{model}",
            [{"role": "user", "content": "Say OK"}],
            [{"type": "function", "function": {"name": "noop"}}],
            {
                "max_tokens": 8,
                "temperature": 0,
                "reasoning_effort": "high",
                "thinking": {"type": "enabled"},
                "tool_choice": "auto",
            },
        )

    assert captured["path"] == "/chat/completions"
    assert captured["body"]["model"] == model
    assert captured["body"]["max_tokens"] == 8
    assert captured["body"]["temperature"] == 0
    assert "tools" not in captured["body"]
    assert "tool_choice" not in captured["body"]
    assert "reasoning_effort" not in captured["body"]
    assert "thinking" not in captured["body"]
    assert result["content"] == [{"type": "text", "text": "OK"}]


@pytest.mark.parametrize("model", ANTHROPIC_MESSAGES_MODELS)
def test_opencode_go_uses_messages_for_minimax(monkeypatch, model):
    provider = _provider(monkeypatch)
    captured = {}

    def fake_request_messages_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {
            "id": "msg_test",
            "model": model,
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

    with patch.object(provider, "_request_messages_json", side_effect=fake_request_messages_json):
        result = provider.complete(
            f"opencode-go/{model}",
            [
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": "Say OK"},
            ],
            [{"name": "noop", "input_schema": {"type": "object"}}],
            {
                "max_tokens": 8,
                "temperature": 0,
                "stop": "END",
                "thinking": {"type": "enabled"},
            },
        )

    assert captured["path"] == "/messages"
    assert captured["body"]["model"] == model
    assert captured["body"]["max_tokens"] == 8
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["stop_sequences"] == ["END"]
    assert captured["body"]["system"] == [{"type": "text", "text": "Be terse."}]
    assert "tools" not in captured["body"]
    assert "thinking" not in captured["body"]
    assert result["content"] == [{"type": "text", "text": "OK"}]


def test_opencode_go_secret_keys():
    from domain.ai_client.api_key_store import provider_secret_keys

    assert provider_secret_keys("opencode-go") == [
        "OPENCODE_GO_API_KEY",
        "OPENCODE_ZEN_API_KEY",
    ]


def test_opencode_go_detect_available_providers_with_key(monkeypatch):
    from domain.ai_client.providers import detect_available_providers
    from domain.ai_client.providers.opencode_go_provider import OpencodeGoProvider

    monkeypatch.setenv("OPENCODE_GO_API_KEY", "test-opencode-go-key")

    available = detect_available_providers()

    assert isinstance(available["opencode-go"], OpencodeGoProvider)


def test_opencode_go_rejects_unknown_model(monkeypatch):
    provider = _provider(monkeypatch)

    with pytest.raises(RuntimeError, match="unsupported model"):
        provider.complete("opencode-go/not-a-real-model", [{"role": "user", "content": "hi"}], [], {})


def test_opencode_go_stream_parses_openai_sse(monkeypatch):
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
        events = list(provider.stream("kimi-k2.6", [{"role": "user", "content": "Say OK"}], [], {"max_tokens": 8}))

    assert captured["path"] == "/chat/completions"
    assert captured["body"]["model"] == "kimi-k2.6"
    assert captured["body"]["stream_options"] == {"include_usage": True}
    assert events[0] == {"type": "content_delta", "delta": {"type": "text", "text": "O"}}
    assert events[1] == {"type": "content_delta", "delta": {"type": "text", "text": "K"}}
    assert events[-1]["type"] == "stream_end"
    assert events[-1]["usage"]["total_tokens"] == 3
    assert response.closed is True


def test_opencode_go_stream_parses_anthropic_sse(monkeypatch):
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

    def fake_request_messages_stream(path, body):
        captured["path"] = path
        captured["body"] = body
        return response

    with patch.object(provider, "_request_messages_stream", side_effect=fake_request_messages_stream):
        events = list(provider.stream("minimax-m2.7", [{"role": "user", "content": "Say OK"}], [], {"max_tokens": 8}))

    assert captured["path"] == "/messages"
    assert captured["body"]["model"] == "minimax-m2.7"
    assert events[0] == {"type": "content_delta", "delta": {"type": "text", "text": "OK"}}
    assert events[-1]["type"] == "stream_end"
    assert events[-1]["usage"] == {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    assert response.closed is True


def _live_enabled():
    return (
        os.environ.get("RUMI_OPENCODE_GO_LIVE_TEST") == "1"
        and bool(os.environ.get("OPENCODE_GO_API_KEY") or os.environ.get("OPENCODE_ZEN_API_KEY"))
    )


@pytest.mark.live
@pytest.mark.skipif(not _live_enabled(), reason="set RUMI_OPENCODE_GO_LIVE_TEST=1 and an OpenCode Go API key")
@pytest.mark.parametrize("model", ALL_MODELS)
def test_opencode_go_live_complete(model):
    from domain.ai_client.providers.opencode_go_provider import OpencodeGoProvider

    provider = OpencodeGoProvider()
    result = provider.complete(
        model,
        [{"role": "user", "content": "Reply with exactly: OK"}],
        [],
        {"max_tokens": 8},
    )
    assert result["content"]


@pytest.mark.live
@pytest.mark.skipif(not _live_enabled(), reason="set RUMI_OPENCODE_GO_LIVE_TEST=1 and an OpenCode Go API key")
@pytest.mark.parametrize("model", ALL_MODELS)
def test_opencode_go_live_stream(model):
    from domain.ai_client.providers.opencode_go_provider import OpencodeGoProvider

    provider = OpencodeGoProvider()
    events = list(
        provider.stream(
            model,
            [{"role": "user", "content": "Say OK"}],
            [],
            {"max_tokens": 8},
        )
    )
    assert events
