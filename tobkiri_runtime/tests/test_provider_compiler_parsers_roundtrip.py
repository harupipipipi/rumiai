from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_openai_parser_roundtrips_to_standard_response():
    from domain.ai_client.provider_compiler.base import CompiledProviderRequest
    from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler

    ir = OpenAIChatCompiler().parse_response(
        {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
        CompiledProviderRequest(api_family="openai_chat", provider_id="openai", model="m", path=""),
    )

    assert ir.to_standard_response()["content"] == [{"type": "text", "text": "ok"}]
    assert ir.to_standard_response()["usage"] == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}


def test_openai_responses_compiler_builds_input_items():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.openai_responses import OpenAIResponsesCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    compiled = OpenAIResponsesCompiler().compile_complete(
        PlannedProviderRequest(
            ir=legacy_standard_messages_to_ir([{"role": "user", "content": "hello"}], "c"),
            model="gpt-test",
            provider_capabilities={"provider_id": "openai", "api_family": "openai_responses"},
        )
    )

    assert compiled.path == "/responses"
    assert compiled.body["input"] == [{"role": "user", "content": "hello"}]
