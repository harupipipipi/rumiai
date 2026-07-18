from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_tool_protocol_maps_invalid_google_tool_names_and_preserves_original():
    from domain.tool.provider_adapter import adapt_rumi_tools_to_provider_tools, decode_provider_tool_call_to_rumi_tool_call

    tools, mapping, definitions = adapt_rumi_tools_to_provider_tools(
        [{"type": "function", "function": {"name": "External Send", "parameters": {"type": "object"}}}],
        {"quirks": {"tool_name_regex": "^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$"}},
    )

    assert tools[0]["function"]["name"] == "External_Send"
    assert definitions[0].name == "External Send"
    call = decode_provider_tool_call_to_rumi_tool_call({"id": "1", "function": {"name": "External_Send", "arguments": "{}"}}, mapping)
    assert call.name == "External Send"


def test_tool_result_image_artifacts_and_approval_are_preserved():
    from domain.tool.result_codec import encode_tool_result_to_ir_blocks

    blocks = encode_tool_result_to_ir_blocks(
        {
            "status": "ok",
            "data": {"approval_required": True},
            "artifacts": [{"path": "/tmp/image.png", "mime_type": "image/png"}],
            "result": "ok",
        },
        tool_call_id="tc",
        name="capture",
    )

    assert blocks[0].tool_result.approval_required is True
    assert blocks[0].tool_result.artifacts[0]["path"] == "/tmp/image.png"
    assert any(block.type == "image" for block in blocks)


def test_parallel_tool_calls_are_serialized_when_provider_disallows_parallel():
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir import RumiChatIR

    planned = plan_model_request(
        RumiChatIR(conversation_id="c"),
        "m",
        {"provider_id": "x", "api_family": "openai_compatible", "supports_tool_calling": True, "supports_parallel_tool_calls": False},
        [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
        {},
        {},
    )

    assert planned.params["parallel_tool_calls"] is False


def test_cerebras_strict_function_tools_add_strict_and_no_extra_properties():
    from domain.tool.provider_adapter import adapt_rumi_tools_to_provider_tools

    provider_tools, _mapping, _definitions = adapt_rumi_tools_to_provider_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "lookup_city",
                    "description": "Lookup a city.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                            "filters": {
                                "type": "object",
                                "properties": {"country": {"type": "string"}},
                            },
                        },
                        "required": ["city", "filters"],
                    },
                },
            }
        ],
        {"quirks": {"strict_function_tools": True}},
    )

    function_def = provider_tools[0]["function"]
    assert function_def["strict"] is True
    assert function_def["parameters"] == {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "filters": {
                "type": "object",
                "properties": {"country": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
        },
        "required": ["city", "filters"],
        "additionalProperties": False,
    }


def test_provider_safe_tool_payload_strips_local_metadata_for_cerebras():
    from domain.chat.progress_tool import assistant_progress_provider_tool
    from domain.tool.schema_adapter import provider_safe_tool_definitions

    provider_tools = provider_safe_tool_definitions(
        [
            {
                "type": "function",
                "metadata": {"local_policy": "confirm"},
                "category": "computer",
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
        {"provider_id": "cerebras", "quirks": {"strict_function_tools": True}},
    )

    assert [set(tool) for tool in provider_tools] == [{"type", "function"}, {"type", "function"}]
    assert "metadata" not in json.dumps(provider_tools)
    assert provider_tools[0]["function"]["strict"] is True
    assert provider_tools[0]["function"]["parameters"]["additionalProperties"] is False
    assert provider_tools[1]["function"]["strict"] is True
    assert provider_tools[1]["function"]["parameters"]["additionalProperties"] is False
