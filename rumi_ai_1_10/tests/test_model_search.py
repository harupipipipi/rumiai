from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _profile(profile_id, **extra):
    provider_id, model_id = profile_id.split("/", 1)
    return {
        "profile_id": profile_id,
        "qualified_model_id": profile_id,
        "provider_id": provider_id,
        "model_id": model_id,
        "display_name": model_id,
        "type": "chat",
        "configured": extra.pop("configured", True),
        **extra,
    }


def test_search_models_filters_by_capabilities():
    from domain.ai_client.model_search import search_models

    profiles = [
        _profile("openai/gpt-5", supports_vision=True, supports_tool_calling=True, supports_thinking=True, supports_fast=False, speed_tier="balanced", knowledge_level=92),
        _profile("local/fast", supports_vision=False, supports_tool_calling=False, supports_thinking=False, supports_fast=True, speed_tier="fast", knowledge_level=30),
    ]

    result = search_models(
        {
            "requires": {"vision": True, "tool_calling": True, "thinking": True},
            "min_knowledge_level": 85,
            "max_results": 5,
        },
        profiles=profiles,
    )

    assert [item["profile_id"] for item in result["models"]] == ["openai/gpt-5"]
    assert result["filters_applied"]["requires"]["vision"] is True


def test_recommend_model_reports_reason_codes():
    from domain.ai_client.model_search import recommend_model

    result = recommend_model(
        {"requires": {"vision": True}, "max_results": 2},
        profiles=[_profile("google/gemini", supports_vision=True, supports_tool_calling=True, supports_thinking=True, supports_fast=True, speed_tier="fast", knowledge_level=85)],
    )

    assert result["selected_model"]["profile_id"] == "google/gemini"
    assert "requires_vision" in result["reason_codes"]
