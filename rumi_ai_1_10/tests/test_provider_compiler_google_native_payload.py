from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provider_payloads"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_google_native_compiler_matches_text_image_tool_snapshot():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir(
            [
                {"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "tc", "function": {"name": "lookup", "arguments": "{}"}}]},
            ],
            "c",
        ),
        model="gemma-4-31b-it",
        provider_capabilities={"provider_id": "google", "api_family": "google_native"},
        provider_tools=[{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
    )

    body = GoogleNativeCompiler().compile_complete(planned).body
    assert body == json.loads((FIXTURES / "google_native_text_image_tool.json").read_text())


def test_google_native_parser_handles_multiple_parts():
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
    from domain.ai_client.provider_compiler.base import CompiledProviderRequest

    parsed = GoogleNativeCompiler().parse_response(
        {"candidates": [{"content": {"parts": [{"text": "visible"}, {"text": "thought", "thought": True}, {"functionCall": {"id": "tc", "name": "lookup", "args": {"q": "x"}}}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2, "totalTokenCount": 3}},
        CompiledProviderRequest(api_family="google_native", provider_id="google", model="m", path="", metadata={}),
    )

    assert parsed.content[0].text == "visible"
    assert parsed.content[1].tool_call.name == "lookup"
    assert parsed.metadata["thinking"]["transcript"] == "thought"


def test_google_native_compiler_normalizes_gemma_thinking_level():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    compiler = GoogleNativeCompiler()
    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "qa"}], "c"),
        model="gemma-4-31b-it",
        provider_capabilities={"provider_id": "google", "api_family": "google_native"},
        provider_tools=[],
        params={"thinking_level": "none"},
    )

    body = compiler.compile_complete(planned).body

    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"
