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


def test_search_models_includes_vision_models_and_compact_queries_by_default():
    from domain.ai_client.model_search import models_for_group, search_models

    profiles = [
        _profile(
            "cerebras/gemma-4-31b",
            display_name="Gemma 4 31B via Cerebras",
            provider_display_name="Cerebras",
            type="vision",
            supports_vision=True,
            supports_image_input=True,
            supports_tool_calling=True,
        ),
    ]

    result = search_models({"query": "gemma4", "max_results": 5}, profiles=profiles)
    group_models = models_for_group("default", {"model_groups": {"default": {"allowed_models": []}}}, profiles=profiles)

    assert [item["profile_id"] for item in result["models"]] == ["cerebras/gemma-4-31b"]
    assert "vision" in result["filters_applied"]["type"]
    assert [item["profile_id"] for item in group_models] == ["cerebras/gemma-4-31b"]


def test_recommend_model_reports_reason_codes():
    from domain.ai_client.model_search import recommend_model

    result = recommend_model(
        {"requires": {"vision": True}, "max_results": 2},
        profiles=[_profile("google/gemini", supports_vision=True, supports_tool_calling=True, supports_thinking=True, supports_fast=True, speed_tier="fast", knowledge_level=85)],
    )

    assert result["selected_model"]["profile_id"] == "google/gemini"
    assert "requires_vision" in result["reason_codes"]


def test_get_model_capabilities_reuses_profile_catalog(monkeypatch):
    from domain.ai_client import model_search
    from domain.ai_client import model_runtime_settings
    from ecosystem.defaultspack.backend.ai_client import provider_catalog

    calls = {"profiles": 0, "models": 0}

    def fake_list_profile_catalog():
        calls["profiles"] += 1
        return [
            _profile(
                "cerebras/gemma-4-31b",
                supports_vision=True,
                supports_tool_calling=True,
                supports_thinking=False,
            ),
            _profile("openai/text-embedding-3-small", type="embedding"),
        ]

    def fail_list_model_catalog():
        calls["models"] += 1
        raise AssertionError("embedding profiles already came from the profile catalog")

    class EmptyRuntimeSettingsService:
        def get_settings(self):
            return {}

        def runtime_defined_profiles(self, settings):
            return []

    model_search.clear_profile_catalog_cache()
    monkeypatch.setattr(provider_catalog, "list_profile_catalog", fake_list_profile_catalog)
    monkeypatch.setattr(provider_catalog, "list_model_catalog", fail_list_model_catalog)
    monkeypatch.setattr(model_runtime_settings, "ModelRuntimeSettingsService", EmptyRuntimeSettingsService)

    first = model_search.get_model_capabilities("cerebras/gemma-4-31b")
    second = model_search.get_model_capabilities("cerebras/gemma-4-31b")

    assert first["profile_id"] == "cerebras/gemma-4-31b"
    assert second["profile_id"] == "cerebras/gemma-4-31b"
    assert calls == {"profiles": 1, "models": 0}

    model_search.clear_profile_catalog_cache()


def test_profile_catalog_cache_key_does_not_walk_secrets_dir(monkeypatch, tmp_path):
    from domain.ai_client import model_search
    from domain.ai_client import model_runtime_settings
    from ecosystem.defaultspack.backend.ai_client import provider_catalog

    secrets_dir = tmp_path / "secrets"
    nested_dir = secrets_dir / "nested" / "deep"
    nested_dir.mkdir(parents=True)
    (nested_dir / "unrelated.json").write_text("{}", encoding="utf-8")
    (secrets_dir / "provider_api_keys.json").write_text('{"cerebras":"secret"}', encoding="utf-8")

    calls = {"profiles": 0}

    def fake_list_profile_catalog():
        calls["profiles"] += 1
        return [
            _profile(
                "cerebras/gemma-4-31b",
                supports_vision=True,
                supports_tool_calling=True,
                supports_thinking=False,
            ),
            _profile("openai/text-embedding-3-small", type="embedding"),
        ]

    class EmptyRuntimeSettingsService:
        def get_settings(self):
            return {}

        def runtime_defined_profiles(self, settings):
            return []

    def fail_rglob(self, pattern):
        raise AssertionError("profile catalog cache key must not recursively walk secrets dir")

    model_search.clear_profile_catalog_cache()
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(secrets_dir))
    monkeypatch.setattr(Path, "rglob", fail_rglob)
    monkeypatch.setattr(provider_catalog, "list_profile_catalog", fake_list_profile_catalog)
    monkeypatch.setattr(
        provider_catalog,
        "list_model_catalog",
        lambda: (_ for _ in ()).throw(AssertionError("embedding profile should come from profile catalog")),
    )
    monkeypatch.setattr(model_runtime_settings, "ModelRuntimeSettingsService", EmptyRuntimeSettingsService)

    first = model_search.get_model_capabilities("cerebras/gemma-4-31b")
    second = model_search.get_model_capabilities("cerebras/gemma-4-31b")

    assert first["profile_id"] == "cerebras/gemma-4-31b"
    assert second["profile_id"] == "cerebras/gemma-4-31b"
    assert calls == {"profiles": 1}

    model_search.clear_profile_catalog_cache()
