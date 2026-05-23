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
