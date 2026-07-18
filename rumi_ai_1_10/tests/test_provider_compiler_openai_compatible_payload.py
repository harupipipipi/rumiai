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


def test_openai_compatible_omits_tool_choice_without_tools():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "call:computer.apps{}"}], "c"),
        model="gemma-4-31b",
        provider_capabilities={"provider_id": "cerebras", "api_family": "openai_compatible"},
        params={"tool_choice": "auto", "parallel_tool_calls": True},
    )

    body = OpenAICompatibleCompiler().compile_complete(planned).body

    assert "tools" not in body
    assert "tool_choice" not in body
    assert "parallel_tool_calls" not in body


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


def test_openai_compatible_strips_tool_metadata_before_provider_payload():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
    from domain.chat.progress_tool import assistant_progress_provider_tool
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "call:computer.apps{}"}], "c"),
        model="gemma-4-31b",
        provider_capabilities={
            "provider_id": "cerebras",
            "api_family": "openai_compatible",
            "supports_tool_calling": True,
            "quirks": {"strict_function_tools": True},
        },
        provider_tools=[
            {
                "type": "function",
                "metadata": {"risk": "medium"},
                "function": {
                    "name": "computer_use",
                    "description": "Use the computer.",
                    "metadata": {"display_name": "Computer"},
                    "parameters": {
                        "type": "object",
                        "properties": {"action": {"type": "string"}},
                        "required": ["action"],
                    },
                },
            },
            assistant_progress_provider_tool(),
        ],
        params={"tool_choice": "auto"},
    )

    body = OpenAICompatibleCompiler().compile_complete(planned).body

    assert body["tool_choice"] == "auto"
    assert [set(tool) for tool in body["tools"]] == [{"type", "function"}, {"type", "function"}]
    assert "metadata" not in json.dumps(body["tools"])
    assert all(tool["function"].get("strict") is True for tool in body["tools"])


def test_openai_compatible_cerebras_strips_assistant_reasoning_content():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "open"}], "c"),
        model="gemma-4-31b",
        provider_capabilities={
            "provider_id": "cerebras",
            "api_family": "openai_compatible",
            "quirks": {"drop_assistant_reasoning_content": True},
        },
    )

    messages = [
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "I should call the computer tool.",
            "tool_calls": [
                {
                    "id": "tc",
                    "type": "function",
                    "function": {"name": "computer_use", "arguments": "{}"},
                }
            ],
        }
    ]

    normalized = OpenAICompatibleCompiler._normalize_provider_messages(planned, messages)

    assert "reasoning_content" not in normalized[0]
    assert normalized[0]["tool_calls"][0]["function"]["name"] == "computer_use"


def test_openai_compatible_provider_cerebras_build_request_strips_assistant_reasoning_content():
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        provider_id="cerebras",
        known_models=[{"id": "cerebras/gemma-4-31b", "model_id": "gemma-4-31b"}],
        credential_required=False,
    )

    messages = [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "I should call the computer tool.",
            "tool_calls": [
                {
                    "id": "tc",
                    "type": "function",
                    "function": {"name": "computer_use", "arguments": "{}"},
                }
            ],
        }
    ]

    converted = provider.build_request(messages)

    assert "reasoning_content" not in converted[0]
    assert converted[0]["tool_calls"][0]["function"]["name"] == "computer_use"


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
