from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


ZEN_REASONING_PROFILE_ID = "opencode-zen/deepseek-v4-flash-free"


def test_dynamic_catalog_models_are_projected_into_profile_picker():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import _merge_model_profiles

    profiles = [
        {
            "profile_id": "openrouter/free",
            "qualified_model_id": "openrouter/free",
            "provider_id": "openrouter",
            "model_id": "free",
            "display_name": "Free Models Router",
        }
    ]
    models = [
        {
            "id": ZEN_REASONING_PROFILE_ID,
            "qualified_model_id": ZEN_REASONING_PROFILE_ID,
            "provider_id": "opencode-zen",
            "model_id": "deepseek-v4-flash-free",
            "display_name": "DeepSeek V4 Flash Free via OpenCode Zen",
            "metadata": {"inventory_source": "curated_fallback"},
        }
    ]

    merged = _merge_model_profiles(profiles, models)

    assert [profile["profile_id"] for profile in merged] == [
        ZEN_REASONING_PROFILE_ID,
    ]
    assert merged[0]["provider_id"] == "opencode-zen"
    assert merged[0]["metadata"]["inventory_source"] == "curated_fallback"


def test_configured_zen_fallback_joins_nonempty_global_catalog(monkeypatch):
    from ecosystem.defaultspack.backend.ai_client import provider_catalog

    openrouter_model = {
        "id": "openrouter/free",
        "qualified_model_id": "openrouter/free",
        "provider_id": "openrouter",
        "model_id": "free",
        "display_name": "Free Models Router",
    }
    zen_model = {
        "id": ZEN_REASONING_PROFILE_ID,
        "qualified_model_id": ZEN_REASONING_PROFILE_ID,
        "provider_id": "opencode-zen",
        "provider": "opencode-zen",
        "model_id": "deepseek-v4-flash-free",
        "display_name": "DeepSeek V4 Flash Free via OpenCode Zen",
        "metadata": {"inventory_source": "curated_fallback"},
    }

    class _RuntimeClient:
        def list_models(self, provider=None):
            if provider and provider != "opencode-zen":
                return []
            return [zen_model]

    def fake_invoke(contract_id, operation, payload):
        del operation, payload
        if contract_id == provider_catalog._MODEL_CATALOG_CONTRACT:
            return {"models": [openrouter_model]}
        if contract_id == provider_catalog._MODEL_PROFILE_CONTRACT:
            return {"profiles": [openrouter_model]}
        if contract_id == provider_catalog._PROVIDER_REGISTRY_CONTRACT:
            return {"providers": []}
        raise AssertionError(contract_id)

    monkeypatch.setattr(provider_catalog, "_runtime_client", lambda: _RuntimeClient())
    monkeypatch.setattr(provider_catalog, "_invoke", fake_invoke)

    model_ids = {item["id"] for item in provider_catalog.list_model_catalog()}
    profile_ids = {item["profile_id"] for item in provider_catalog.list_profile_catalog()}

    assert ZEN_REASONING_PROFILE_ID in model_ids
    assert ZEN_REASONING_PROFILE_ID in profile_ids


def _catalog_model() -> dict:
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_model_catalog

    return next(
        item
        for item in list_model_catalog(provider="opencode-zen")
        if item["id"] == ZEN_REASONING_PROFILE_ID
    )


def _catalog_profile() -> dict:
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog

    return next(
        item
        for item in list_profile_catalog()
        if item["profile_id"] == ZEN_REASONING_PROFILE_ID
    )


def test_defaultspack_catalog_exposes_deepseek_v4_flash_free_capability_metadata():
    model = _catalog_model()
    profile = _catalog_profile()

    assert model["model_id"] == "deepseek-v4-flash-free"
    assert profile["qualified_model_id"] == ZEN_REASONING_PROFILE_ID

    for item in (model, profile):
        assert item["supports_tool_calling"] is False
        assert item["supports_thinking"] is True
        assert item["supports_vision"] is False
        assert item["metadata"]["supports_tool_calling"] is False
        assert item["metadata"]["supports_thinking"] is True
        assert item["metadata"]["supports_vision"] is False
        assert item["model_capabilities"].get("tool_calling", False) is False
        assert item["model_capabilities"]["thinking"] is True
        assert item["model_capabilities"].get("vision", False) is False

    assert "thinking" in model["capability_tags"]
    assert "vision" not in model["capability_tags"]
    assert "primary_chat" in profile["recommended_roles"]
    assert "vision_ocr" not in profile["recommended_roles"]


def test_defaultspack_model_search_returns_deepseek_free_for_capability_query():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
    from domain.ai_client.model_search import search_models

    result = search_models(
        {
            "query": "deepseek v4 flash free",
            "provider_id": "opencode-zen",
            "requires": {"thinking": True},
            "max_results": 10,
        },
        profiles=list_profile_catalog(),
    )

    assert [item["profile_id"] for item in result["models"]] == [
        ZEN_REASONING_PROFILE_ID
    ]
    assert result["models"][0]["supports_tool_calling"] is False
    assert result["models"][0]["supports_thinking"] is True
    assert result["models"][0]["supports_vision"] is False
