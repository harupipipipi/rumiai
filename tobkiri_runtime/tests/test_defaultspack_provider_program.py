from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_required_provider_program_has_one_canonical_registry_owner():
    from domain.ai_client.provider_program import provider_program_manifests
    from domain.ai_client.providers import validate_provider_program_coverage

    manifests = provider_program_manifests()

    assert len(manifests) == 79
    assert validate_provider_program_coverage() == []
    assert all(manifest["models"] == [] for manifest in manifests.values())


def test_local_openai_runtimes_discover_served_models_without_credentials(monkeypatch):
    from unittest.mock import patch

    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    monkeypatch.setenv("RUMI_DEFAULTSPACK_ENABLE_LOCAL_PROVIDERS", "1")
    AIClient._instance = None
    with patch.object(
        OpenAICompatibleProvider,
        "_fetch_remote_models",
        return_value=[
            {
                "id": "vllm/served-model",
                "model_id": "served-model",
                "provider_id": "vllm",
                "type": "chat",
                "metadata": {"source": "remote_models_endpoint"},
            }
        ],
    ), patch.object(OpenAICompatibleProvider, "_load_remote_model_cache", return_value=None):
        client = AIClient()
        models = client.list_models(provider="vllm")

    assert [model["qualified_model_id"] for model in models] == ["vllm/served-model"]


def test_ollama_uses_its_live_openai_compatible_models_endpoint_without_credentials(monkeypatch):
    from unittest.mock import patch

    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    monkeypatch.setenv("RUMI_DEFAULTSPACK_ENABLE_LOCAL_PROVIDERS", "1")
    AIClient._instance = None
    with patch.object(
        OpenAICompatibleProvider,
        "_fetch_remote_models",
        return_value=[
            {
                "id": "ollama/locally-loaded-model",
                "model_id": "locally-loaded-model",
                "provider_id": "ollama",
                "type": "chat",
                "metadata": {"source": "remote_models_endpoint"},
            }
        ],
    ), patch.object(OpenAICompatibleProvider, "_load_remote_model_cache", return_value=None):
        models = AIClient().list_models(provider="ollama")

    assert [model["qualified_model_id"] for model in models] == ["ollama/locally-loaded-model"]


def test_loopback_openai_compatible_connection_discovers_models_without_storing_a_fake_key(tmp_path, monkeypatch):
    from unittest.mock import patch

    from domain.ai_client.api_key_store import provider_named_api_keys, set_provider_api_key
    from domain.ai_client.providers import _custom_openai_provider_manifests, _instantiate_manifest_provider
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    saved = set_provider_api_key(
        "huggingface-tgi",
        "",
        pack_root=tmp_path,
        api_id="local",
        name="Local TGI",
        base_url="http://127.0.0.1:8080/v1",
        credential_mode="none",
    )

    assert saved["success"] is True
    assert saved["configured"] is True
    connections = provider_named_api_keys("huggingface-tgi", pack_root=tmp_path)
    assert connections[0]["credential_mode"] == "none"
    assert connections[0]["configured"] is True
    assert not (tmp_path / "user_data" / "secrets" / f"{saved['key']}.json").exists()

    # Build the executable adapter from the saved endpoint, with no fallback
    # model JSON and no API key requirement.
    monkeypatch.setattr(
        "domain.ai_client.providers.provider_named_api_keys",
        lambda provider_id="": connections if provider_id in {"", "huggingface-tgi"} else [],
    )
    manifest = _custom_openai_provider_manifests()["huggingface-tgi"]
    assert manifest["credential_required"] is False
    assert manifest["config"]["model_list_requires_auth"] is False
    with patch.object(OpenAICompatibleProvider, "_fetch_remote_models", return_value=[]):
        provider = _instantiate_manifest_provider(manifest)
    assert provider is not None
    assert provider._api_key == ""
    assert provider._credential_required is False


def test_huggingface_inference_uses_its_live_models_endpoint_without_a_checked_in_model_list(monkeypatch):
    from unittest.mock import patch

    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    spec = OPENAI_COMPATIBLE_PROVIDER_SPECS["huggingface-inference"]
    assert spec["default_base_url"] == "https://router.huggingface.co/v1"
    assert spec["curated_models"] == []

    monkeypatch.setenv("HF_TOKEN", "test-hf-token")
    AIClient._instance = None
    with patch.object(
        OpenAICompatibleProvider,
        "_fetch_remote_models",
        return_value=[
            {
                "id": "deepseek-ai/DeepSeek-R1:fastest",
                "model_id": "deepseek-ai/DeepSeek-R1:fastest",
                "provider_id": "huggingface-inference",
                "type": "chat",
                "metadata": {"source": "remote_models_endpoint"},
            }
        ],
    ), patch.object(OpenAICompatibleProvider, "_load_remote_model_cache", return_value=None):
        models = AIClient().list_models(provider="huggingface-inference")

    assert [model["model_id"] for model in models] == ["deepseek-ai/DeepSeek-R1:fastest"]
    assert all(model["provider_id"] == "huggingface-inference" for model in models)


def test_github_models_uses_its_account_catalog_and_openai_compatible_inference_endpoint():
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    spec = OPENAI_COMPATIBLE_PROVIDER_SPECS["github-models"]
    manifest = _openai_compatible_spec_manifest(spec)
    provider = OpenAICompatibleProvider.from_manifest(manifest)

    assert spec["curated_models"] == []
    assert provider._base_url == "https://models.github.ai/inference"
    assert provider._remote_model_base_url == "https://models.github.ai/catalog"
    assert provider._headers()["X-GitHub-Api-Version"] == "2026-03-10"
    page, cursor = provider._remote_models_page([{"id": "openai/gpt-4.1", "name": "OpenAI GPT-4.1"}])
    assert page == [{"id": "openai/gpt-4.1", "name": "OpenAI GPT-4.1"}]
    assert cursor == ""


def test_openai_compatible_provider_specs_do_not_freeze_glm_dashscope_or_siliconflow_models():
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    expected_endpoints = {
        "alibaba-dashscope": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "glm": "https://api.z.ai/api/paas/v4",
        "siliconflow": "https://api.siliconflow.cn/v1",
    }
    for provider_id, endpoint in expected_endpoints.items():
        spec = OPENAI_COMPATIBLE_PROVIDER_SPECS[provider_id]
        assert spec["curated_models"] == []
        provider = OpenAICompatibleProvider.from_manifest(_openai_compatible_spec_manifest(spec))
        assert provider._base_url == endpoint
        assert provider._remote_model_list_path == "/models"


def test_anthropic_models_endpoint_paginates_and_replaces_its_static_fallback(monkeypatch):
    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.anthropic_provider import AnthropicProvider

    pages = {
        "": {
            "data": [{"id": "claude-live-a", "display_name": "Claude Live A", "capabilities": {"thinking": {"supported": True}}}],
            "has_more": True,
            "last_id": "claude-live-a",
        },
        "claude-live-a": {
            "data": [{"id": "claude-live-b", "display_name": "Claude Live B", "capabilities": {"image_input": {"supported": True}}}],
            "has_more": False,
        },
    }
    monkeypatch.setattr(AnthropicProvider, "_fetch_models_page", lambda self, after_id="": pages[after_id])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-token")
    AnthropicProvider._MODEL_INVENTORY_CACHE.clear()
    AIClient._instance = None

    models = AIClient().list_models(provider="anthropic")

    assert [model["model_id"] for model in models] == ["claude-live-a", "claude-live-b"]
    assert all(model["metadata"]["source"] == "native_models_endpoint" for model in models)
    assert "vision" in models[1]["capabilities"]


def test_openai_spec_uses_live_models_endpoint_without_a_checked_in_model_list():
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    spec = OPENAI_COMPATIBLE_PROVIDER_SPECS["openai"]
    assert spec["curated_models"] == []
    provider = OpenAICompatibleProvider.from_manifest(_openai_compatible_spec_manifest(spec))
    assert provider._base_url == "https://api.openai.com/v1"
    assert provider._remote_model_list_path == "/models"


def test_google_models_endpoint_paginates_and_replaces_the_curated_fallback(monkeypatch):
    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.google_provider import GoogleProvider

    pages = {
        "": {
            "models": [{"name": "models/gemini-live-a", "displayName": "Gemini Live A", "supportedGenerationMethods": ["generateContent"]}],
            "nextPageToken": "page-two",
        },
        "page-two": {
            "models": [{"name": "models/gemini-live-b", "displayName": "Gemini Live B", "supportedGenerationMethods": ["embedContent"]}],
        },
    }
    monkeypatch.setattr(GoogleProvider, "_fetch_native_models_page", lambda self, token="": pages[token])
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-token")
    GoogleProvider._MODEL_INVENTORY_CACHE.clear()
    AIClient._instance = None

    models = AIClient().list_models(provider="google")

    assert [model["model_id"] for model in models] == ["gemini-live-a", "gemini-live-b"]
    assert all(model["metadata"]["source"] == "native_models_endpoint" for model in models)
