from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _catalog_and_models(provider_id: str):
    from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map

    catalog = get_provider_catalog_map()
    models = {item["id"]: item for item in get_all_known_models(provider_id)}
    return catalog[provider_id], models


def test_groq_manifest_first_runtime_provider_and_allowlist(monkeypatch):
    from domain.ai_client.providers import detect_available_providers

    provider, models = _catalog_and_models("groq")

    assert provider["availability"]["supports_invoke"] is True
    assert provider["metadata"]["adapter"] == "openai_compatible"
    assert provider["metadata"]["default_base_url"] == "https://api.groq.com/openai/v1"
    assert provider["default_model_for"]["chat"] == "openai/gpt-oss-120b"
    assert provider["default_model_for"]["fast"] == "openai/gpt-oss-20b"
    assert {
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",
    }.issubset(models)
    assert not any("compound" in model_id.lower() for model_id in models)

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    assert "groq" in detect_available_providers()


def test_cerebras_manifest_first_runtime_provider(monkeypatch):
    from domain.ai_client.providers import detect_available_providers

    provider, models = _catalog_and_models("cerebras")

    assert provider["availability"]["supports_invoke"] is True
    assert provider["metadata"]["adapter"] == "openai_compatible"
    assert provider["metadata"]["default_base_url"] == "https://api.cerebras.ai/v1"
    assert provider["default_model_for"]["coding"] == "zai-glm-4.7"
    assert {"cerebras/gpt-oss-120b", "cerebras/zai-glm-4.7"}.issubset(models)
    assert provider["metadata"]["config"]["service_tier_request_injection"] == "explicit_only"

    monkeypatch.setenv("CEREBRAS_API_KEY", "test-cerebras-key")
    assert "cerebras" in detect_available_providers()


def test_nvidia_manifest_first_runtime_provider_accepts_either_key(monkeypatch):
    from domain.ai_client.providers import detect_available_providers

    provider, models = _catalog_and_models("nvidia")

    assert provider["availability"]["supports_invoke"] is True
    assert provider["metadata"]["adapter"] == "openai_compatible"
    assert provider["metadata"]["default_base_url"] == "https://integrate.api.nvidia.com/v1"
    assert provider["env_vars"] == ["NVIDIA_API_KEY", "NGC_API_KEY"]
    assert {
        "nvidia/nvidia/llama-3.1-nemotron-70b-instruct",
        "nvidia/meta/llama-3.1-70b-instruct",
    }.issubset(models)

    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NGC_API_KEY", "test-ngc-key")
    assert "nvidia" in detect_available_providers()


def test_cloud_provider_keys_are_persistable_in_secret_store():
    from domain.ai_client.api_key_store import provider_secret_keys

    assert provider_secret_keys("groq") == ["GROQ_API_KEY"]
    assert provider_secret_keys("cerebras") == ["CEREBRAS_API_KEY"]
    assert provider_secret_keys("nvidia") == ["NVIDIA_API_KEY", "NGC_API_KEY"]


def test_moonshot_manifest_first_runtime_provider(monkeypatch):
    from domain.ai_client.providers import detect_available_providers

    provider, models = _catalog_and_models("moonshotai")

    assert provider["availability"]["supports_invoke"] is True
    assert provider["metadata"]["adapter"] == "openai_compatible"
    assert provider["metadata"]["default_base_url"] == "https://api.moonshot.ai/v1"
    assert provider["default_model_for"]["agent"] == "kimi-k2-0711-preview"
    assert {"moonshotai/kimi-k2-0711-preview", "moonshotai/moonshot-v1-8k"}.issubset(models)

    monkeypatch.setenv("MOONSHOT_API_KEY", "test-moonshot-key")
    assert "moonshotai" in detect_available_providers()


def test_xiaomi_mimo_direct_catalog_is_separate_and_not_runtime_enabled(monkeypatch):
    from domain.ai_client.providers import detect_available_providers, get_provider_catalog_map

    catalog = get_provider_catalog_map()

    assert catalog["gitlawb-opengateway"]["provider_id"] == "gitlawb-opengateway"
    assert catalog["xiaomi-mimo"]["availability"]["supports_invoke"] is False
    assert catalog["xiaomi-mimo-global"]["availability"]["supports_invoke"] is False
    assert catalog["xiaomi-mimo-cn"]["availability"]["supports_invoke"] is False
    assert catalog["xiaomi-mimo-global"]["metadata"]["config"]["do_not_fallback_to_other_region"] is True
    assert catalog["xiaomi-mimo-cn"]["metadata"]["config"]["do_not_reuse_credentials_across_regions"] is True

    with patch.dict(
        os.environ,
        {
            "XIAOMI_MIMO_GLOBAL_API_KEY": "test-global",
            "XIAOMI_MIMO_GLOBAL_BASE_URL": "https://mimo.example/v1",
        },
        clear=False,
    ):
        assert "xiaomi-mimo-global" not in detect_available_providers()
