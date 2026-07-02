from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


MINIMAX_PROFILE_ID = "opencode-zen/minimax-m3-free"
MIMO_FREE_PROFILE_ID = "opencode-zen/mimo-v2.5-free"


def _catalog_model() -> dict:
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_model_catalog

    return next(item for item in list_model_catalog(provider="opencode-zen") if item["id"] == MINIMAX_PROFILE_ID)


def _catalog_profile() -> dict:
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog

    return next(item for item in list_profile_catalog() if item["profile_id"] == MINIMAX_PROFILE_ID)


def test_defaultspack_catalog_exposes_minimax_m3_free_capability_metadata():
    model = _catalog_model()
    profile = _catalog_profile()

    assert model["model_id"] == "minimax-m3-free"
    assert profile["qualified_model_id"] == MINIMAX_PROFILE_ID

    for item in (model, profile):
        assert item["supports_tool_calling"] is False
        assert item["supports_thinking"] is True
        assert item["supports_vision"] is True
        assert item["metadata"]["supports_tool_calling"] is False
        assert item["metadata"]["supports_thinking"] is True
        assert item["metadata"]["supports_vision"] is True
        assert item["model_capabilities"]["capabilities"]["tool_calling"] is False
        assert item["model_capabilities"]["capabilities"]["thinking"] is True
        assert item["model_capabilities"]["capabilities"]["vision"] is True

    assert {"thinking", "vision"}.issubset(model["capability_tags"])
    assert {"deep_reasoning", "vision_ocr"}.issubset(profile["recommended_roles"])


def test_defaultspack_model_search_returns_minimax_m3_free_for_capability_query():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
    from domain.ai_client.model_search import search_models

    result = search_models(
        {
            "query": "minimax m3 free",
            "provider_id": "opencode-zen",
            "requires": {"thinking": True, "vision": True},
            "max_results": 10,
        },
        profiles=list_profile_catalog(),
    )

    assert [item["profile_id"] for item in result["models"]] == [MINIMAX_PROFILE_ID]
    assert result["models"][0]["supports_tool_calling"] is False
    assert result["models"][0]["supports_thinking"] is True
    assert result["models"][0]["supports_vision"] is True


def test_defaultspack_catalog_exposes_opencode_zen_mimo_v25_free_capability_metadata():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_model_catalog, list_profile_catalog

    model = next(item for item in list_model_catalog(provider="opencode-zen") if item["id"] == MIMO_FREE_PROFILE_ID)
    profile = next(item for item in list_profile_catalog() if item["profile_id"] == MIMO_FREE_PROFILE_ID)

    assert model["model_id"] == "mimo-v2.5-free"
    assert profile["qualified_model_id"] == MIMO_FREE_PROFILE_ID

    for item in (model, profile):
        assert item["supports_tool_calling"] is True
        assert item["supports_thinking"] is True
        assert item["supports_vision"] is True
        assert item["metadata"]["transport"] == "openai_chat_completions"
        assert item["metadata"]["endpoint_path"] == "/v1/chat/completions"
        assert item["metadata"]["supports_tool_calling"] is True
        assert item["metadata"]["supports_thinking"] is True
        assert item["metadata"]["supports_vision"] is True
        assert item["model_capabilities"]["capabilities"]["tool_calling"] is True
        assert item["model_capabilities"]["capabilities"]["thinking"] is True
        assert item["model_capabilities"]["capabilities"]["vision"] is True

    assert {"tools", "thinking", "vision"}.issubset(model["capability_tags"])
    assert "coding" in profile["allowed_roles"]
    assert {"deep_reasoning", "vision_ocr"}.issubset(profile["recommended_roles"])


def test_defaultspack_model_search_returns_opencode_zen_mimo_v25_free_for_coding_query():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
    from domain.ai_client.model_search import search_models

    result = search_models(
        {
            "query": "mimo v2.5 free coding",
            "provider_id": "opencode-zen",
            "requires": {"thinking": True, "tool_calling": True},
            "max_results": 10,
        },
        profiles=list_profile_catalog(),
    )

    assert [item["profile_id"] for item in result["models"]] == [MIMO_FREE_PROFILE_ID]
    assert result["models"][0]["supports_tool_calling"] is True
    assert result["models"][0]["supports_thinking"] is True
