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


def test_search_models_matches_multi_word_queries_across_model_separators():
    from domain.ai_client.model_search import search_models

    profiles = [
        _profile(
            "gitlawb-opengateway/mimo-v2-omni",
            display_name="MiMo V2 Omni via Gitlawb OpenGateway",
            provider_display_name="Gitlawb OpenGateway",
            supports_vision=True,
            capability_tags=["vision"],
            recommended_roles=["primary_chat", "vision_ocr"],
        ),
    ]

    result = search_models({"query": "mimo omni", "max_results": 5}, profiles=profiles)

    assert [item["profile_id"] for item in result["models"]] == ["gitlawb-opengateway/mimo-v2-omni"]


def test_recommend_model_reports_reason_codes():
    from domain.ai_client.model_search import recommend_model

    result = recommend_model(
        {"requires": {"vision": True}, "max_results": 2},
        profiles=[_profile("google/gemini", supports_vision=True, supports_tool_calling=True, supports_thinking=True, supports_fast=True, speed_tier="fast", knowledge_level=85)],
    )

    assert result["selected_model"]["profile_id"] == "google/gemini"
    assert "requires_vision" in result["reason_codes"]


def test_named_api_key_profile_keeps_base_model_capabilities(monkeypatch):
    from domain.ai_client import model_search

    base_profiles = [
        _profile(
            "google/gemma-4-31b-it",
            supports_vision=True,
            supports_tool_calling=True,
            supports_thinking=True,
            thinking_levels=["minimal", "high"],
        )
    ]

    monkeypatch.setattr(
        "domain.ai_client.api_key_store.provider_named_api_keys",
        lambda provider_id=None: [
            {
                "provider_id": "google",
                "api_id": "gemma4-test",
                "configured": True,
                "allowed_models": ["gemma-4-31b-it"],
                "default_model": "gemma-4-31b-it",
                "name": "Gemma 4 test",
            }
        ],
    )
    monkeypatch.setattr("domain.ai_client.api_key_store.read_provider_api_key", lambda provider_id, api_id: "secret")

    profiles = base_profiles + model_search._named_api_key_profiles(base_profiles)
    caps = model_search.get_model_capabilities("google/gemma4-test/gemma-4-31b-it", profiles=profiles)

    assert caps["profile_id"] == "google/gemma4-test/gemma-4-31b-it"
    assert caps["model_id"] == "gemma-4-31b-it"
    assert caps["supports_tool_calling"] is True
    assert caps["supports_vision"] is True
    assert caps["metadata"]["api_bound"] is True
