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
    assert {
        "cerebras/gpt-oss-120b",
        "cerebras/zai-glm-4.7",
        "cerebras/qwen-3-235b-a22b-instruct-2507",
        "cerebras/llama3.1-8b",
    }.issubset(models)
    assert provider["metadata"]["config"]["service_tier_request_injection"] == "explicit_only"

    monkeypatch.setenv("CEREBRAS_API_KEY", "test-cerebras-key")
    assert "cerebras" in detect_available_providers()


def test_cerebras_openai_compatible_params_match_model_contract():
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    captured = {}
    provider = OpenAICompatibleProvider(
        provider_id="cerebras",
        api_key="test-cerebras-key",
        default_base_url="https://api.cerebras.ai/v1",
        credential_required=False,
        known_models=[
            {
                "id": "cerebras/gpt-oss-120b",
                "model_id": "gpt-oss-120b",
                "display_name": "GPT OSS 120B",
                "capabilities": {"reasoning": True},
                "metadata": {
                    "request_example": {
                        "max_completion_tokens": 32768,
                        "temperature": 1,
                        "top_p": 1,
                        "reasoning_effort": "high",
                    }
                },
            },
            {
                "id": "cerebras/llama3.1-8b",
                "model_id": "llama3.1-8b",
                "display_name": "Llama 3.1 8B",
                "capabilities": {"reasoning": False},
                "metadata": {
                    "request_defaults": {
                        "max_completion_tokens": 2048,
                        "temperature": 0.2,
                        "top_p": 1,
                    }
                },
            },
        ],
    )

    def fake_request_json(path, body):
        captured.setdefault("bodies", []).append(body)
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        provider.complete(
            "gpt-oss-120b",
            [{"role": "user", "content": "hi"}],
            [],
            {"thinking_level": "high", "max_tokens": 123},
        )
        provider.complete(
            "llama3.1-8b",
            [{"role": "user", "content": "hi"}],
            [],
            {"thinking_level": "medium", "max_tokens": 99},
        )

    gpt_body, llama_body = captured["bodies"]
    assert gpt_body["max_completion_tokens"] == 123
    assert gpt_body["temperature"] == 1
    assert gpt_body["top_p"] == 1
    assert gpt_body["reasoning_effort"] == "high"
    assert "max_tokens" not in gpt_body

    assert llama_body["max_completion_tokens"] == 99
    assert llama_body["temperature"] == 0.2
    assert llama_body["top_p"] == 1
    assert "reasoning_effort" not in llama_body
    assert "max_tokens" not in llama_body


def test_cerebras_explicit_none_thinking_does_not_restore_default_reasoning_effort():
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    captured = {}
    provider = OpenAICompatibleProvider(
        provider_id="cerebras",
        api_key="test-cerebras-key",
        default_base_url="https://api.cerebras.ai/v1",
        credential_required=False,
        known_models=[
            {
                "id": "cerebras/gpt-oss-120b",
                "model_id": "gpt-oss-120b",
                "display_name": "GPT OSS 120B",
                "capabilities": {"reasoning": True},
            },
        ],
    )

    def fake_request_json(path, body):
        captured["body"] = body
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        provider.complete(
            "gpt-oss-120b",
            [{"role": "user", "content": "hi"}],
            [],
            {"thinking_level": "none"},
        )

    body = captured["body"]
    assert body["temperature"] == 1
    assert body["top_p"] == 1
    assert "reasoning_effort" not in body


def test_cerebras_thinking_normalization_only_emits_supported_reasoning_params():
    from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

    service = ModelRuntimeSettingsService()

    gpt = service.normalize_for_provider("cerebras", "gpt-oss-120b", "high")
    gpt_none = service.normalize_for_provider("cerebras", "gpt-oss-120b", "none")
    llama = service.normalize_for_provider("cerebras", "llama3.1-8b", "high")

    assert gpt["provider_params"] == {"reasoning_effort": "high"}
    assert gpt_none["provider_params"] == {}
    assert llama["provider_params"] == {}


def test_nvidia_manifest_first_runtime_provider_accepts_either_key(monkeypatch):
    from domain.ai_client.providers import detect_available_providers

    provider, models = _catalog_and_models("nvidia")

    assert provider["availability"]["supports_invoke"] is True
    assert provider["metadata"]["adapter"] == "openai_compatible"
    assert provider["metadata"]["default_base_url"] == "https://integrate.api.nvidia.com/v1"
    assert provider["env_vars"] == ["NVIDIA_API_KEY", "NGC_API_KEY"]
    assert provider["default_model_for"]["coding"] == "qwen/qwen3-coder-480b-a35b-instruct"
    assert provider["default_model_for"]["fast"] == "nvidia/nvidia-nemotron-nano-9b-v2"
    assert {
        "nvidia/nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "nvidia/nvidia/llama-3.3-nemotron-super-49b-v1",
        "nvidia/meta/llama-3.3-70b-instruct",
        "nvidia/openai/gpt-oss-120b",
        "nvidia/openai/gpt-oss-20b",
        "nvidia/qwen/qwen3-coder-480b-a35b-instruct",
        "nvidia/deepseek-ai/deepseek-v4-flash",
    }.issubset(models)

    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NGC_API_KEY", "test-ngc-key")
    assert "nvidia" in detect_available_providers()


def test_cloud_provider_keys_are_persistable_in_secret_store():
    from domain.ai_client.api_key_store import provider_secret_keys

    assert provider_secret_keys("groq") == ["GROQ_API_KEY"]
    assert provider_secret_keys("gitlawb-opengateway") == ["GITLAWB_OPENGATEWAY_API_KEY"]
    assert provider_secret_keys("opencode-go") == ["OPENCODE_GO_API_KEY", "OPENCODE_ZEN_API_KEY"]
    assert provider_secret_keys("cerebras") == ["CEREBRAS_API_KEY"]
    assert provider_secret_keys("nvidia") == ["NVIDIA_API_KEY", "NGC_API_KEY"]
    assert provider_secret_keys("xiaomi-token-plan-sgp") == [
        "XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY",
        "XIAOMI_MIMO_TOKEN_PLAN_API_KEY",
        "MIMO_API_KEY",
    ]


def test_named_token_plan_key_maps_back_to_long_provider_id(tmp_path, monkeypatch):
    from domain.ai_client.api_key_store import (
        load_provider_api_keys_into_env,
        provider_has_api_key,
        provider_named_api_keys,
        set_provider_api_key,
    )

    for env_name in (
        "XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY",
        "XIAOMI_MIMO_TOKEN_PLAN_API_KEY",
        "MIMO_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)

    set_provider_api_key(
        "xiaomi-token-plan-sgp",
        "test-token",
        name="MiMo Token Plan SGP",
        default_model="mimo-v2.5-pro",
        pack_root=tmp_path,
    )

    assert provider_has_api_key("xiaomi-token-plan-sgp", pack_root=tmp_path) is True
    assert provider_named_api_keys("xiaomi-token-plan-sgp", pack_root=tmp_path)[0]["provider_id"] == "xiaomi-token-plan-sgp"

    loaded = load_provider_api_keys_into_env(pack_root=tmp_path)

    assert loaded["xiaomi-token-plan-sgp"] is True
    assert os.environ["XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY"] == "test-token"


def test_cloud_model_capability_false_values_are_preserved():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog

    profiles = {item["profile_id"]: item for item in list_profile_catalog()}

    cerebras_gpt_oss = profiles["cerebras/gpt-oss-120b"]
    cerebras_zai = profiles["cerebras/zai-glm-4.7"]
    nvidia_nemotron = profiles["nvidia/nvidia/llama-3.3-nemotron-super-49b-v1.5"]

    for profile in (cerebras_gpt_oss, cerebras_zai, nvidia_nemotron):
        assert profile["supports_vision"] is False
        assert "vision" not in profile["capability_tags"]
        assert profile["supports_tool_calling"] is True

    assert cerebras_gpt_oss["model_capabilities"]["capabilities"]["parallel_tool_calls"] is False
    assert cerebras_zai["model_capabilities"]["capabilities"]["parallel_tool_calls"] is True
    assert nvidia_nemotron["model_capabilities"]["capabilities"]["parallel_tool_calls"] is True


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
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_model_catalog, list_provider_catalog

    catalog = get_provider_catalog_map()

    assert catalog["gitlawb-opengateway"]["provider_id"] == "gitlawb-opengateway"
    assert catalog["xiaomi-mimo"]["availability"]["supports_invoke"] is False
    assert catalog["xiaomi-mimo-global"]["availability"]["supports_invoke"] is False
    assert catalog["xiaomi-mimo-cn"]["availability"]["supports_invoke"] is False
    assert catalog["xiaomi-token-plan-sgp"]["availability"]["supports_invoke"] is True
    assert catalog["xiaomi-token-plan-sgp"]["metadata"]["adapter"] == "python_entrypoint"
    assert catalog["xiaomi-token-plan-sgp"]["metadata"]["default_base_url"] == "https://token-plan-sgp.xiaomimimo.com/v1"
    assert catalog["xiaomi-mimo-global"]["metadata"]["config"]["do_not_fallback_to_other_region"] is True
    assert catalog["xiaomi-mimo-cn"]["metadata"]["config"]["do_not_reuse_credentials_across_regions"] is True
    global_plan = catalog["xiaomi-mimo-global"]["subscription_plans"][0]
    cn_plan = catalog["xiaomi-mimo-cn"]["metadata"]["subscription_plans"][0]
    assert global_plan["id"] == "mimo_orbit_100t_grant_if_available"
    assert global_plan["token_quota_label"] == "100T tokens"
    assert global_plan["region"] == "global"
    assert global_plan["requires_manual_signup"] is True
    assert global_plan["do_not_auto_enable"] is True
    assert cn_plan["region"] == "cn"
    assert cn_plan["region_scoped"] is True

    api_providers = {provider["provider_id"]: provider for provider in list_provider_catalog()}
    assert api_providers["xiaomi-mimo-global"]["subscription_plans"][0]["id"] == global_plan["id"]

    global_models = {model["id"]: model for model in list_model_catalog("xiaomi-mimo-global")}
    assert global_models["xiaomi-mimo-global/mimo-v2.5-pro"]["metadata"]["subscription_plan_ids"] == [
        global_plan["id"]
    ]

    with patch.dict(
        os.environ,
        {
            "XIAOMI_MIMO_GLOBAL_API_KEY": "test-global",
            "XIAOMI_MIMO_GLOBAL_BASE_URL": "https://mimo.example/v1",
        },
        clear=False,
    ):
        assert "xiaomi-mimo-global" not in detect_available_providers()

    monkeypatch.setenv("XIAOMI_MIMO_TOKEN_PLAN_SGP_API_KEY", "test-token-plan")
    assert "xiaomi-token-plan-sgp" in detect_available_providers()


def test_xiaomi_token_plan_catalog_models_are_runtime_and_tool_capable():
    provider, models = _catalog_and_models("xiaomi-token-plan-sgp")

    assert provider["availability"]["supports_invoke"] is True
    assert provider["metadata"]["config"]["auth_header"] == "api-key"
    assert provider["default_model_for"]["coding"] == "mimo-v2.5-pro"
    assert "xiaomi-token-plan-sgp/mimo-v2.5-pro" in models

    pro = models["xiaomi-token-plan-sgp/mimo-v2.5-pro"]
    assert pro["type"] == "reasoning"
    assert pro["defaults"]["chat"] is True
    assert "tool_calls" in pro["capabilities"]
