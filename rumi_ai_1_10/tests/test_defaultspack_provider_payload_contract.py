from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

pytestmark = pytest.mark.contract


def test_openai_provider_build_request_and_parse_tool_calls_contract():
    from domain.ai_client.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider()
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "tc", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "tc", "content": "ok"},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "u"}}]},
    ]

    request = provider.build_request(messages)
    parsed = provider.parse_response(
        {
            "choices": [
                {
                    "message": {"content": "", "tool_calls": [{"id": "tc2", "function": {"name": "lookup", "arguments": "{}"}}]},
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    )

    assert request[0]["tool_calls"][0]["function"]["name"] == "lookup"
    assert request[1]["role"] == "tool"
    assert request[2]["content"][0]["type"] == "image_url"
    assert parsed["content"][1] == {"type": "tool_use", "id": "tc2", "name": "lookup", "input": "{}"}


def test_non_vision_provider_payload_contains_no_image_blocks():
    from domain.ai_client.provider_compiler.registry import compile_complete
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    ir = legacy_standard_messages_to_ir(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "read it"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,aaa"}},
                ],
            }
        ],
        "c",
    )

    planned = plan_model_request(
        ir,
        "text-only-model",
        {
            "provider_id": "local",
            "api_family": "openai_chat",
            "supports_vision": False,
            "supported_content_blocks": ["text"],
        },
        [],
        {},
        {},
    )
    compiled = compile_complete(planned)

    dumped = json.dumps(compiled.body)
    assert "image_url" not in dumped
    assert "data:image/" not in dumped
    assert all(block.type not in {"image", "image_url"} for message in planned.ir.messages for block in message.content)
    assert any(action.action == "vision_bridge_required" for action in planned.bridge_actions)
    assert any(item.feature == "image_url" for item in planned.dropped_features)


def test_google_provider_tool_name_mapping_and_native_body_contract():
    from domain.ai_client.providers.google_provider import GoogleProvider

    tool = {"type": "function", "function": {"name": "External Send", "description": "send", "parameters": {"type": "object", "properties": {}}}}
    name_map, reverse = GoogleProvider._tool_name_maps([tool])
    provider = GoogleProvider()
    body = provider._native_body(
        "gemma-4-31b-it",
        [
            {"role": "system", "content": "system"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "tc", "function": {"name": "External Send", "arguments": "{\"x\":1}"}}]},
            {"role": "tool", "tool_call_id": "tc", "name": "External Send", "content": "{\"ok\":true}"},
        ],
        [tool],
        {"thinking_level": "high"},
        name_map,
    )
    text, thought, finish, tool_uses = provider._native_extract_parts(
        {"candidates": [{"content": {"parts": [{"functionCall": {"id": "tc2", "name": "External_Send", "args": {"x": 1}}}]}}]},
        reverse,
    )

    assert body["tools"][0]["functionDeclarations"][0]["name"] == "External_Send"
    assert body["contents"][0]["parts"][0]["functionCall"]["name"] == "External_Send"
    assert body["contents"][1]["parts"][0]["functionResponse"]["name"] == "External_Send"
    assert tool_uses[0]["name"] == "External Send"
    assert finish == "tool_calls"
    assert text == thought == ""


def test_openai_compatible_cerebras_reasoning_none_contract(monkeypatch):
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        provider_id="cerebras",
        api_key="key",
        base_url="https://example.test",
        known_models=[{"id": "cerebras/gpt-oss-120b", "model_id": "gpt-oss-120b", "supports_thinking": True}],
    )
    captured = {}
    monkeypatch.setattr(provider, "_request_json", lambda path, body: captured.setdefault("body", body) or {"choices": [{"message": {"content": "ok"}}]})

    provider.complete("gpt-oss-120b", [{"role": "user", "content": "hi"}], [], {"max_tokens": 7, "thinking_level": "none"})

    assert captured["body"]["max_completion_tokens"] == 7
    assert "reasoning_effort" not in captured["body"]
