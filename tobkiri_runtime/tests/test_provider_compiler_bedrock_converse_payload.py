from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provider_payloads"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_bedrock_converse_compiler_tool_config_snapshot_and_parser():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.bedrock_converse import BedrockConverseCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    compiler = BedrockConverseCompiler()
    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "assistant", "content": None, "tool_calls": [{"id": "tc", "function": {"name": "lookup", "arguments": "{}"}}]}], "c"),
        model="anthropic.claude-test",
        provider_capabilities={"provider_id": "bedrock", "api_family": "bedrock_converse"},
        provider_tools=[{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
    )
    compiled = compiler.compile_complete(planned)
    parsed = compiler.parse_response({"output": {"message": {"content": [{"text": "ok"}, {"toolUse": {"toolUseId": "tc2", "name": "lookup", "input": {}}}]}}, "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3}}, compiled)

    assert compiled.body == json.loads((FIXTURES / "bedrock_converse_tool_config.json").read_text())
    assert parsed.content[1].tool_call.id == "tc2"
