from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_openai_chat_stream_parser_emits_text_reasoning_and_end():
    from domain.ai_client.provider_compiler.base import CompiledProviderRequest
    from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler

    events = OpenAIChatCompiler().parse_stream_chunk(
        {"choices": [{"delta": {"content": "hi", "reasoning_content": "think"}, "finish_reason": "stop"}], "usage": {"total_tokens": 3}},
        CompiledProviderRequest(api_family="openai_chat", provider_id="openai", model="m", path=""),
    )

    assert [event.type for event in events] == ["content_delta", "reasoning_delta", "stream_end"]
    assert events[-1].usage == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 3,
    }


def test_openai_chat_stream_parser_keeps_usage_only_terminal_chunk():
    from domain.ai_client.provider_compiler.base import CompiledProviderRequest
    from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler

    events = OpenAIChatCompiler().parse_stream_chunk(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 4,
                "total_tokens": 6,
            },
        },
        CompiledProviderRequest(
            api_family="openai_chat",
            provider_id="openai",
            model="m",
            path="",
        ),
    )

    assert [event.type for event in events] == ["stream_end"]
    assert events[0].usage["total_tokens"] == 6


def test_anthropic_stream_parser_emits_reasoning_tools_and_usage():
    from domain.ai_client.provider_compiler.anthropic_messages import (
        AnthropicMessagesCompiler,
    )
    from domain.ai_client.provider_compiler.base import CompiledProviderRequest

    compiler = AnthropicMessagesCompiler()
    compiled = CompiledProviderRequest(
        api_family="anthropic_messages",
        provider_id="anthropic",
        model="m",
        path="",
    )
    state = {"id": "tool-1", "name": "lookup"}
    payloads = [
        {
            "type": "content_block_delta",
            "delta": {"type": "thinking_delta", "thinking": "considering"},
            "_compiler_state": {},
        },
        {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": "{\"q\":\"x\"}"},
            "_compiler_state": state,
        },
        {
            "type": "content_block_stop",
            "_compiler_state": state,
        },
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"input_tokens": 2, "output_tokens": 3},
            "_compiler_state": {},
        },
    ]
    events = [
        event
        for payload in payloads
        for event in compiler.parse_stream_chunk(payload, compiled)
    ]

    assert [event.type for event in events] == [
        "reasoning_delta",
        "tool_call_delta",
        "tool_call_end",
        "stream_end",
    ]
    assert events[-1].usage["total_tokens"] == 5


def test_google_native_stream_parser_emits_tool_events():
    from domain.ai_client.provider_compiler.base import CompiledProviderRequest
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler

    events = GoogleNativeCompiler().parse_stream_chunk(
        {"candidates": [{"content": {"parts": [{"functionCall": {"id": "tc", "name": "lookup", "args": {}}}]}}]},
        CompiledProviderRequest(api_family="google_native", provider_id="google", model="m", path="", metadata={}),
    )

    assert [event.type for event in events] == ["tool_call_start", "tool_call_delta", "tool_call_end"]
