from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provider_payloads"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_openai_chat_compiler_matches_basic_snapshot():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "hello"}], "c"),
        model="gpt-test",
        provider_capabilities={"provider_id": "openai", "api_family": "openai_chat"},
        params={"temperature": 0.2},
    )
    compiled = OpenAIChatCompiler().compile_complete(planned)

    assert compiled.path == "/chat/completions"
    assert compiled.body == json.loads((FIXTURES / "openai_chat_basic.json").read_text())


def test_openai_chat_compiler_preserves_tool_calls_snapshot():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir(
            [{"role": "assistant", "content": None, "tool_calls": [{"id": "tc", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]}],
            "c",
        ),
        model="gpt-test",
        provider_capabilities={"provider_id": "openai", "api_family": "openai_chat"},
        provider_tools=[{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
    )

    assert OpenAIChatCompiler().compile_complete(planned).body == json.loads((FIXTURES / "openai_chat_tool_call.json").read_text())
