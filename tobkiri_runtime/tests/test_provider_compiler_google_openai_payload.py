from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_google_openai_compiler_sanitizes_and_reverse_maps_tool_names():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.google_openai import GoogleOpenAICompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    compiler = GoogleOpenAICompiler()
    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "hello"}], "c"),
        model="gemini-test",
        provider_capabilities={"provider_id": "google", "api_family": "google_openai"},
        provider_tools=[{"type": "function", "function": {"name": "External Send", "parameters": {"type": "object"}}}],
    )
    compiled = compiler.compile_complete(planned)
    parsed = compiler.parse_response(
        {"choices": [{"message": {"content": "", "tool_calls": [{"id": "tc", "function": {"name": "External_Send", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]},
        compiled,
    )

    assert compiled.body["tools"][0]["function"]["name"] == "External_Send"
    assert parsed.content[1].tool_call.name == "External Send"
