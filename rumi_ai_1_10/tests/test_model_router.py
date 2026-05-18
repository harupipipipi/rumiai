from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_router_selects_vision_tool_model_inside_group():
    from domain.ai_client.model_router import ModelRoutingRequest, route_model_request

    profiles = [
        {"profile_id": "stub/default", "qualified_model_id": "stub/default", "provider_id": "stub", "model_id": "default", "type": "chat", "configured": True, "supports_vision": False, "supports_tool_calling": False, "supports_thinking": False, "speed_tier": "fast", "knowledge_level": 0},
        {"profile_id": "google/gemini", "qualified_model_id": "google/gemini", "provider_id": "google", "model_id": "gemini", "type": "chat", "configured": True, "supports_vision": True, "supports_tool_calling": True, "supports_thinking": True, "speed_tier": "balanced", "knowledge_level": 85},
    ]
    decision = route_model_request(
        ModelRoutingRequest(
            has_images=True,
            requires_tool_calling=True,
            requested_thinking_level="high",
            preferred_model="stub/default",
            preferred_group="default",
            auto_route_within_group=True,
            settings={"model_groups": {"default": {"allowed_models": []}}},
        ),
        profiles=profiles,
    )

    assert decision.selected_model == "google/gemini"
    assert decision.bridge_required is False
    assert "requires_vision" in decision.reason_codes


def test_router_returns_bridge_plan_when_no_vision_model_available():
    from domain.ai_client.model_router import ModelRoutingRequest, route_model_request

    profiles = [
        {"profile_id": "local/text", "qualified_model_id": "local/text", "provider_id": "local", "model_id": "text", "type": "chat", "configured": True, "supports_vision": False, "supports_tool_calling": False, "supports_thinking": False, "speed_tier": "fast", "knowledge_level": 30},
    ]
    decision = route_model_request(
        ModelRoutingRequest(has_images=True, preferred_model="local/text", settings={"on_switch_to_non_vision_with_images": "auto_bridge"}),
        profiles=profiles,
    )

    assert decision.bridge_required is True
    assert decision.bridge_plan["type"] == "vision_bridge"


def test_router_keeps_requested_gemma_4_when_profile_catalog_preserves_capabilities():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
    from domain.ai_client.model_router import ModelRoutingRequest, route_model_request

    decision = route_model_request(
        ModelRoutingRequest(
            user_text="好きな食べ物教えて〜",
            requested_tools=["computer_use", "browser_computer"],
            requires_tool_calling=True,
            requested_thinking_level="low",
            preferred_model="google/gemma-4-31b-it",
            preferred_group="default",
            auto_route_within_group=True,
            settings={"model_groups": {"default": {"allowed_models": []}}},
        ),
        profiles=list_profile_catalog(),
    )

    assert decision.selected_model == "google/gemma-4-31b-it"
    assert "same_model" in decision.reason_codes
