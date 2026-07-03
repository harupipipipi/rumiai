from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


MIMO_PROFILE_ID = "opencode-zen/mimo-v2.5-free"


def _catalog_model() -> dict:
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_model_catalog

    return next(item for item in list_model_catalog(provider="opencode-zen") if item["id"] == MIMO_PROFILE_ID)


def _catalog_profile() -> dict:
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog

    return next(item for item in list_profile_catalog() if item["profile_id"] == MIMO_PROFILE_ID)


def test_defaultspack_catalog_exposes_mimo_v2_5_free_capability_metadata():
    model = _catalog_model()
    profile = _catalog_profile()

    assert model["model_id"] == "mimo-v2.5-free"
    assert profile["qualified_model_id"] == MIMO_PROFILE_ID

    for item in (model, profile):
        assert item["supports_tool_calling"] is False
        assert item["supports_thinking"] is True
        assert item["supports_vision"] is False
        assert item["metadata"]["supports_tool_calling"] is False
        assert item["metadata"]["supports_thinking"] is True
        assert item["metadata"]["supports_vision"] is False
        assert item["model_capabilities"]["capabilities"]["tool_calling"] is False
        assert item["model_capabilities"]["capabilities"]["thinking"] is True
        assert item["model_capabilities"]["capabilities"]["vision"] is False

    assert "thinking" in model["capability_tags"]
    assert "deep_reasoning" in profile["recommended_roles"]


def test_defaultspack_model_search_returns_mimo_v2_5_free_for_capability_query():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
    from domain.ai_client.model_search import search_models

    result = search_models(
        {
            "query": "mimo v2.5 free",
            "provider_id": "opencode-zen",
            "requires": {"thinking": True},
            "max_results": 10,
        },
        profiles=list_profile_catalog(),
    )

    assert [item["profile_id"] for item in result["models"]] == [MIMO_PROFILE_ID]
    assert result["models"][0]["supports_tool_calling"] is False
    assert result["models"][0]["supports_thinking"] is True
    assert result["models"][0]["supports_vision"] is False
