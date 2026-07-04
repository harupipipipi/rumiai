from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _ir(blocks, role="user"):
    from domain.chat.ir import RumiChatIR, RumiIRMessage

    return RumiChatIR(conversation_id="c", messages=[RumiIRMessage(role=role, content=blocks)])


def test_request_planner_drops_reasoning_for_non_reasoning_model():
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir_blocks import RumiIRBlock

    planned = plan_model_request(
        _ir([RumiIRBlock(type="reasoning", text="hidden", model_visible=False)]),
        "local/model",
        {"provider_id": "local", "api_family": "openai_compatible", "supports_reasoning": False, "supported_content_blocks": ["text"]},
        [],
        {"thinking_level": "high"},
        {},
    )

    assert planned.params["thinking_level"] == "none"
    assert any(item.feature == "reasoning" for item in planned.dropped_features)


def test_request_planner_drops_internal_deepthink_params_before_provider_payload():
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir_blocks import RumiIRBlock

    planned = plan_model_request(
        _ir([RumiIRBlock(type="text", text="hi")]),
        "local/model",
        {"provider_id": "local", "api_family": "openai_compatible", "supports_reasoning": True, "supported_content_blocks": ["text"]},
        [],
        {
            "deepthink_enabled": True,
            "deepthink_max_review_iterations": 4,
            "rumi_base_model_override": "xiaomi-token-plan-sgp/mimo-v2.5-pro",
            "rumi_require_intended_base_model": True,
            "temperature": 0.2,
        },
        {},
    )

    assert planned.params == {"temperature": 0.2}


def test_request_planner_bridges_image_and_developer_role():
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir import RumiChatIR, RumiIRMessage
    from domain.chat.ir_blocks import RumiIRBlock

    ir = RumiChatIR(
        conversation_id="c",
        messages=[
            RumiIRMessage(role="developer", content=[RumiIRBlock(type="text", text="be precise")]),
            RumiIRMessage(role="user", content=[RumiIRBlock(type="image_url", data={"image_url": {"url": "u"}})]),
        ],
    )
    planned = plan_model_request(
        ir,
        "local/model",
        {"provider_id": "local", "api_family": "openai_compatible", "supports_vision": False, "supported_roles": ["system", "user", "assistant"], "supported_content_blocks": ["text"]},
        [],
        {},
        {},
    )

    assert planned.ir.messages[0].role == "system"
    assert any(action.action == "vision_bridge_required" for action in planned.bridge_actions)


def test_request_planner_preserves_developer_role_when_supported():
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir import RumiChatIR, RumiIRMessage
    from domain.chat.ir_blocks import RumiIRBlock

    ir = RumiChatIR(
        conversation_id="c",
        messages=[
            RumiIRMessage(role="developer", content=[RumiIRBlock(type="text", text="use terse answers")]),
            RumiIRMessage(role="user", content=[RumiIRBlock(type="text", text="hello")]),
        ],
    )
    planned = plan_model_request(
        ir,
        "local/model",
        {
            "provider_id": "local",
            "api_family": "openai_compatible",
            "supported_roles": ["system", "developer", "user", "assistant"],
            "supported_content_blocks": ["text"],
        },
        [],
        {},
        {},
    )

    assert [message.role for message in planned.ir.messages] == ["developer", "user"]
    assert not any(warning.code == "developer_role_merged" for warning in planned.warnings)


def test_request_planner_marks_tool_calling_unavailable_and_aliases_invalid_names():
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir_blocks import RumiIRBlock

    tool = {"type": "function", "function": {"name": "External Send", "parameters": {"type": "object"}}}
    unavailable = plan_model_request(
        _ir([RumiIRBlock(type="text", text="hi")]),
        "model",
        {"provider_id": "x", "api_family": "openai_compatible", "supports_tool_calling": False, "supported_content_blocks": ["text"]},
        [tool],
        {},
        {},
    )
    available = plan_model_request(
        _ir([RumiIRBlock(type="text", text="hi")]),
        "model",
        {"provider_id": "google", "api_family": "google_openai", "supports_tool_calling": True, "supported_content_blocks": ["text"], "quirks": {"tool_name_regex": "^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$"}},
        [tool],
        {},
        {},
    )

    assert unavailable.provider_tools == []
    assert unavailable.warnings[0].code == "requested_tools_without_provider_attachment"
    assert available.provider_tools[0]["function"]["name"] == "External_Send"
