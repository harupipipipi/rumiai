from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provider_payloads"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_openai_compatible_cerebras_reasoning_none_snapshot():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "hello"}], "c"),
        model="gpt-oss-120b",
        provider_capabilities={"provider_id": "cerebras", "api_family": "openai_compatible", "quirks": {"max_tokens_name": "max_completion_tokens", "drop_reasoning_when_none": True}},
        params={"max_tokens": 7, "thinking_level": "none"},
    )

    assert OpenAICompatibleCompiler().compile_complete(planned).body == json.loads((FIXTURES / "openai_compatible_cerebras_reasoning_none.json").read_text())


def test_openai_compatible_openrouter_preserves_gateway_params():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    params = {
        "reasoning": {"effort": "high"},
        "include_reasoning": True,
        "provider": {"order": ["Groq"], "allow_fallbacks": False},
        "models": ["openai/o3-pro", "z-ai/glm-5.2"],
        "web_search_options": {"search_context_size": "low"},
        "structured_outputs": True,
    }
    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "hello"}], "c"),
        model="cohere/north-mini-code:free",
        provider_capabilities={"provider_id": "openrouter", "api_family": "openai_compatible", "quirks": {}},
        params=params,
    )

    body = OpenAICompatibleCompiler().compile_complete(planned).body

    for key, value in params.items():
        assert body[key] == value


def test_openai_compatible_groq_omits_tool_message_name():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir(
            [
                {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_1", "name": "lookup", "content": "{\"ok\":true}"},
            ],
            "c",
        ),
        model="llama-3.3-70b-versatile",
        provider_capabilities={
            "provider_id": "groq",
            "api_family": "openai_compatible",
            "quirks": {"omit_tool_message_name": True},
        },
        params={},
    )

    body = OpenAICompatibleCompiler().compile_complete(planned).body
    tool_message = next(message for message in body["messages"] if message["role"] == "tool")

    assert "name" not in tool_message
    assert tool_message["tool_call_id"] == "call_1"
