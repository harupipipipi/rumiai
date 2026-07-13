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


def test_jina_discovers_its_live_models_without_a_checked_in_snapshot(monkeypatch):
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    spec = OPENAI_COMPATIBLE_PROVIDER_SPECS["jina-ai"]
    provider = OpenAICompatibleProvider.from_manifest(_openai_compatible_spec_manifest(spec))
    provider._api_key = "jina-key"
    assert spec["curated_models"] == []
    assert provider._base_url == "https://api.jina.ai/v1"
    assert provider._remote_model_list_path == "/models"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return (
                b'{"data":[{"id":"jina-embeddings-v4","name":"Jina Embeddings v4",'
                b'"type":"embedding","input_modalities":["text"],'
                b'"output_modalities":["embeddings"],"context_length":32768}]}'
            )

    seen = {}

    def fake_urlopen(request, **_kwargs):
        seen["url"] = request.full_url
        seen["authorization"] = request.headers.get("Authorization")
        return Response()

    monkeypatch.setattr("domain.ai_client.providers.openai_compatible_provider.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(OpenAICompatibleProvider, "_load_remote_model_cache", lambda _self: None)
    models = provider.list_models()

    assert seen == {"url": "https://api.jina.ai/v1/models", "authorization": "Bearer jina-key"}
    assert [model["model_id"] for model in models] == ["jina-embeddings-v4"]
    assert models[0]["type"] == "embedding"
    assert models[0]["capabilities"]["embeddings"] is True
    assert models[0]["metadata"]["source"] == "remote_models_endpoint"


def test_qianfan_uses_its_authenticated_models_api_without_a_snapshot(monkeypatch):
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_CLASSES, OPENAI_COMPATIBLE_PROVIDER_SPECS

    spec = OPENAI_COMPATIBLE_PROVIDER_SPECS["baidu-qianfan"]
    provider = OPENAI_COMPATIBLE_PROVIDER_CLASSES["baidu-qianfan"].from_manifest(
        _openai_compatible_spec_manifest(spec)
    )
    provider._api_key = "qianfan-key"
    assert spec["curated_models"] == []
    assert provider.BASE_URL == "https://qianfan.baidubce.com/v2"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"object":"list","data":[{"id":"account-custom-model","owned_by":"me","type":"embeddings","context_length":8192}]}'

    seen = {}

    def fake_urlopen(request, **_kwargs):
        seen["url"] = request.full_url
        seen["authorization"] = request.headers.get("Authorization")
        return Response()

    monkeypatch.setattr("domain.ai_client.providers.openai_compatible_provider.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(OpenAICompatibleProvider, "_load_remote_model_cache", lambda _self: None)
    models = provider.list_models()

    assert seen == {
        "url": "https://qianfan.baidubce.com/v2/models",
        "authorization": "Bearer qianfan-key",
    }
    assert [model["model_id"] for model in models] == ["account-custom-model"]
    assert models[0]["metadata"]["source"] == "remote_models_endpoint"
    assert models[0]["type"] == "embedding"
    assert models[0]["context_window"] == 8192
    assert models[0]["capabilities"]["embeddings"] is True


def test_openai_compatible_inventory_accepts_common_catalog_envelopes_and_same_origin_next_links(monkeypatch):
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        provider_id="gateway",
        api_key="gateway-key",
        base_url="https://gateway.example/v1",
        known_models=[],
        remote_model_discovery=True,
    )
    responses = {
        "https://gateway.example/v1/models": {
            "result": {
                "items": [
                    {"name": "account-chat", "features": ["chat-completions", "function-calling"]},
                    {"slug": "account-image", "task": "image-generation", "capabilities": ["text-to-image"]},
                ]
            },
            "links": {"next": "https://gateway.example/v1/models?page=2"},
        },
        "https://gateway.example/v1/models?page=2": {
            "models": ["account-embed"],
            "next_page_token": "",
        },
    }
    requested = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            import json

            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, **_kwargs):
        requested.append(request.full_url)
        return Response(responses[request.full_url])

    monkeypatch.setattr("domain.ai_client.providers.openai_compatible_provider.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(OpenAICompatibleProvider, "_load_remote_model_cache", lambda _self: None)

    models = provider.list_models()

    assert requested == ["https://gateway.example/v1/models", "https://gateway.example/v1/models?page=2"]
    assert [model["model_id"] for model in models] == ["account-chat", "account-image", "account-embed"]
    assert models[0]["capabilities"]["tool_calling"] is True
    assert models[1]["type"] == "image_gen"
    assert models[1]["capabilities"]["image_generation"] is True
    assert models[2]["type"] == "embedding"


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


def test_openai_compatible_provider_specs_use_live_models_endpoints_instead_of_release_lists():
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    for provider_id in (
        "xai", "groq", "together", "deepseek", "fireworks", "cerebras", "sambanova", "perplexity", "mistral", "novita", "deepinfra",
        "friendli", "hyperbolic", "inference-net", "upstage",
        "moonshotai", "nvidia", "nebius", "avian",
    ):
        spec = OPENAI_COMPATIBLE_PROVIDER_SPECS[provider_id]
        assert spec["remote_model_discovery"] is True
        assert spec["curated_models"] == []
        provider = OpenAICompatibleProvider.from_manifest(_openai_compatible_spec_manifest(spec))
        assert provider._remote_model_list_path == ("/models/list" if provider_id == "deepinfra" else "/models")

    perplexity = OpenAICompatibleProvider.from_manifest(
        _openai_compatible_spec_manifest(OPENAI_COMPATIBLE_PROVIDER_SPECS["perplexity"])
    )
    assert perplexity._base_url == "https://api.perplexity.ai/v1"
    novita = OpenAICompatibleProvider.from_manifest(
        _openai_compatible_spec_manifest(OPENAI_COMPATIBLE_PROVIDER_SPECS["novita"])
    )
    assert novita._base_url == "https://api.novita.ai/openai/v1"
    deepinfra = OpenAICompatibleProvider.from_manifest(
        _openai_compatible_spec_manifest(OPENAI_COMPATIBLE_PROVIDER_SPECS["deepinfra"])
    )
    assert deepinfra._remote_model_base_url == "https://api.deepinfra.com"
    assert deepinfra._remote_model_list_path == "/models/list"
    deepinfra_model = deepinfra._normalize_remote_model(
        {"model_name": "deepinfra-live-embedding", "type": "embeddings"}
    )
    assert deepinfra_model is not None
    assert deepinfra_model["model_id"] == "deepinfra-live-embedding"
    assert deepinfra_model["type"] == "embedding"
    kimi = OpenAICompatibleProvider.from_manifest(
        _openai_compatible_spec_manifest(OPENAI_COMPATIBLE_PROVIDER_SPECS["moonshotai"])
    )
    kimi_model = kimi._normalize_remote_model(
        {"id": "kimi-live", "supports_image_in": True, "supports_reasoning": True}
    )
    assert kimi_model is not None
    assert kimi_model["capabilities"]["vision"] is True
    assert kimi_model["capabilities"]["reasoning"] is True

    xai_model = OpenAICompatibleProvider._normalize_remote_model(
        OpenAICompatibleProvider.from_manifest(_openai_compatible_spec_manifest(OPENAI_COMPATIBLE_PROVIDER_SPECS["xai"])),
        {"id": "grok-imagine-video", "output_modalities": ["video"]},
    )
    assert xai_model is not None
    assert xai_model["type"] == "video_gen"
    xai_vision_model = OpenAICompatibleProvider._normalize_remote_model(
        OpenAICompatibleProvider.from_manifest(_openai_compatible_spec_manifest(OPENAI_COMPATIBLE_PROVIDER_SPECS["xai"])),
        {"id": "grok-vision", "input_modalities": ["text", "image"], "output_modalities": ["text"]},
    )
    assert xai_vision_model is not None
    assert xai_vision_model["type"] == "chat"
    assert xai_vision_model["capabilities"]["vision"] is True
    assert xai_vision_model["capabilities"]["image_generation"] is False


def test_openai_compatible_manifest_never_exposes_a_checked_in_model_snapshot():
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    assert OPENAI_COMPATIBLE_PROVIDER_SPECS
    assert all(
        _openai_compatible_spec_manifest(spec)["models"] == []
        for spec in OPENAI_COMPATIBLE_PROVIDER_SPECS.values()
    )


def test_external_provider_catalog_never_uses_curated_model_fallbacks(monkeypatch):
    from domain.ai_client import providers

    monkeypatch.setattr(providers, "_load_model_manifests", lambda _provider_id: [])
    monkeypatch.setattr(providers, "model_manifests_from_provider_components", lambda _provider_id: [])
    monkeypatch.setattr(providers, "_load_known_models_from_entry", lambda _entrypoint: [])
    monkeypatch.setattr(providers, "get_extension_registry", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    assert providers._load_models_for_provider({"provider_id": "openrouter", "entrypoint": ""}) == []
    assert providers.get_best_model_for_provider("openrouter") is None


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


def test_native_openai_models_endpoint_replaces_its_static_fallback(monkeypatch):
    from domain.ai_client.providers.openai_provider import OpenAIProvider

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-token")
    OpenAIProvider._MODEL_INVENTORY_CACHE.clear()
    provider = OpenAIProvider()
    monkeypatch.setattr(
        provider,
        "_fetch_live_models",
        lambda: [
            {"id": "account-chat", "owned_by": "project"},
            {"id": "account-embedding", "owned_by": "project"},
            {"id": "account-image", "owned_by": "project"},
        ],
    )

    models = provider.list_models()

    assert [model["model_id"] for model in models] == [
        "account-chat",
        "account-embedding",
        "account-image",
    ]
    assert [model["type"] for model in models] == ["chat", "embedding", "image_gen"]
    assert all(model["metadata"]["source"] == "native_models_endpoint" for model in models)
    assert OpenAIProvider.KNOWN_MODELS == []


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


def test_cohere_models_endpoint_paginates_and_uses_native_chat_adapter(monkeypatch):
    from domain.ai_client.providers.cohere_provider import CohereProvider

    pages = {
        "": {
            "models": [{"name": "command-live-a", "endpoints": ["chat"], "features": ["chat-completions"], "context_length": 128000}],
            "next_page_token": "page-two",
        },
        "page-two": {
            "models": [{"name": "embed-live-b", "endpoints": ["embed"], "features": ["embeddings"], "context_length": 1024}],
        },
    }
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-token")
    CohereProvider._MODEL_INVENTORY_CACHE.clear()
    provider = CohereProvider()
    monkeypatch.setattr(provider, "_fetch_models_page", lambda token="": pages[token])

    models = provider.list_models()

    assert [model["model_id"] for model in models] == ["command-live-a", "embed-live-b"]
    assert [model["type"] for model in models] == ["chat", "embedding"]
    assert all(model["metadata"]["source"] == "native_models_endpoint" for model in models)

    captured = {}

    def fake_request(method, path, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return {
            "id": "cohere-response",
            "finish_reason": "COMPLETE",
            "message": {"content": [{"type": "text", "text": "live response"}]},
            "usage": {"tokens": {"input_tokens": 3, "output_tokens": 2}},
        }

    monkeypatch.setattr(provider, "_request_json", fake_request)
    response = provider.complete("command-live-a", [{"role": "user", "content": "hello"}], [], {"max_tokens": 32})

    assert captured == {
        "method": "POST",
        "path": "/v2/chat",
        "body": {"model": "command-live-a", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 32},
    }
    assert response["content"] == [{"type": "text", "text": "live response"}]
    assert response["usage"]["total_tokens"] == 5

    def fake_embed_request(method, path, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return {
            "embeddings": {"float": [[0.1, 0.2]]},
            "usage": {"tokens": {"input_tokens": 2}},
        }

    monkeypatch.setattr(provider, "_request_json", fake_embed_request)
    embedding = provider.embed("embed-live-b", "search text")

    assert captured == {
        "method": "POST",
        "path": "/v2/embed",
        "body": {
            "model": "embed-live-b",
            "inputs": [{"content": [{"type": "text", "text": "search text"}]}],
            "input_type": "search_document",
            "embedding_types": ["float"],
        },
    }
    assert embedding == {"embeddings": [[0.1, 0.2]], "usage": {"input_tokens": 2, "total_tokens": 2}}


def test_native_provider_inventory_is_bound_to_the_saved_api_key_without_model_text_input(monkeypatch):
    from domain.ai_client.model_availability import ModelAvailabilityService

    service = ModelAvailabilityService()
    monkeypatch.setattr(
        service,
        "_catalog_models",
        lambda _provider_id: [{"model_id": "account-visible-model", "metadata": {"source": "native_models_endpoint"}}],
    )

    assert service._live_model_ids("cohere") == ["account-visible-model"]


def test_model_availability_discovers_each_named_connection_with_its_own_credentials(monkeypatch):
    import domain.ai_client.client as client_module
    import domain.ai_client.model_availability as availability_module
    from domain.ai_client.model_availability import ModelAvailabilityService

    class Provider:
        _api_key = "primary-key"
        _base_url = "https://primary.example/v1"
        BASE_URL = _base_url

        def list_models(self):
            return [{
                "model_id": "secondary-only" if self._api_key == "secondary-key" else "primary-only",
                "metadata": {"source": "remote_models_endpoint"},
            }]

    runtime_provider = Provider()

    class Client:
        _providers = {"gateway": runtime_provider}

    monkeypatch.setattr(client_module, "AIClient", lambda: Client())
    monkeypatch.setattr(
        availability_module,
        "provider_api_metadata",
        lambda provider_id, api_id, **_kwargs: {"base_url": "https://secondary.example/v1"},
    )
    monkeypatch.setattr(
        availability_module,
        "read_provider_api_key",
        lambda provider_id, api_id, **_kwargs: "secondary-key",
    )

    models = ModelAvailabilityService()._live_model_ids("gateway", "secondary")

    assert models == ["secondary-only"]
    assert runtime_provider._api_key == "primary-key"
    assert runtime_provider._base_url == "https://primary.example/v1"


def test_elevenlabs_discovers_the_key_visible_audio_models_and_invokes_tts(monkeypatch):
    from domain.ai_client.providers import detect_available_providers
    from domain.ai_client.providers.elevenlabs_provider import ElevenLabsProvider

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-key")
    ElevenLabsProvider._MODEL_INVENTORY_CACHE.clear()
    provider = ElevenLabsProvider()
    requests = []
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda method, path, body=None: (
            requests.append((method, path, body))
            or [{"model_id": "tts-live", "name": "TTS live", "can_do_text_to_speech": True}]
        ),
    )

    models = provider.list_models()

    assert requests == [("GET", "/v1/models", None)]
    assert models[0]["model_id"] == "tts-live"
    assert models[0]["type"] == "tts"
    assert models[0]["capabilities"]["tts"] is True

    captured = {}
    monkeypatch.setattr(
        provider,
        "_request_audio",
        lambda path, body: captured.update({"path": path, "body": body}) or b"audio",
    )
    response = provider.tts("elevenlabs/tts-live", "hello", "voice id")

    assert captured == {
        "path": "/v1/text-to-speech/voice%20id",
        "body": {"text": "hello", "model_id": "tts-live"},
    }
    assert response["audio"].startswith("data:audio/mpeg;base64,")
    assert isinstance(detect_available_providers()["elevenlabs"], ElevenLabsProvider)


def test_cloudflare_workers_ai_discovers_account_scoped_models_and_runs_text_generation(monkeypatch):
    from domain.ai_client.providers.cloudflare_workers_ai_provider import CloudflareWorkersAIProvider

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-cloudflare-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-id")
    CloudflareWorkersAIProvider._MODEL_INVENTORY_CACHE.clear()
    provider = CloudflareWorkersAIProvider()
    calls = []

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return {
                "result": [
                    {"id": "@cf/meta/llama", "name": "Llama", "task": {"name": "text-generation"}},
                    {"id": "@cf/stability/image", "name": "Image", "task": {"name": "text-to-image"}},
                    {"id": "@cf/baai/embed", "name": "Embed", "task": {"name": "text-embedding"}},
                ],
                "result_info": {"total_pages": 1},
            }
        return {"result": {"response": "live answer"}}

    monkeypatch.setattr(provider, "_request_json", fake_request)
    models = provider.list_models()
    response = provider.complete("@cf/meta/llama", [{"role": "user", "content": "hello"}], [], {"max_tokens": 8})

    assert calls[0] == ("GET", "/models/search?format=openrouter&page=1&per_page=100", None)
    assert [model["type"] for model in models] == ["chat", "image_gen", "embedding"]
    assert models[1]["capabilities"]["image_generation"] is True
    assert calls[-1] == (
        "POST",
        "/run/@cf/meta/llama",
        {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 8},
    )
    assert response["content"] == [{"type": "text", "text": "live answer"}]


def test_deepgram_discovers_live_stt_tts_models_and_calls_native_tasks(monkeypatch):
    from domain.ai_client.providers.deepgram_provider import DeepgramProvider

    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-deepgram-key")
    DeepgramProvider._MODEL_INVENTORY_CACHE.clear()
    provider = DeepgramProvider()
    requests = []

    def fake_json(method, path, body=None):
        requests.append((method, path, body))
        if method == "GET":
            return {
                "stt": [{"canonical_name": "nova-live", "languages": ["ja"], "streaming": True}],
                "tts": [{"canonical_name": "aura-live", "languages": ["ja"]}],
            }
        return {"results": {"channels": [{"alternatives": [{"transcript": "live transcript"}]}]}}

    monkeypatch.setattr(provider, "_request_json", fake_json)
    models = provider.list_models()
    transcript = provider.transcribe("deepgram/nova-live", "https://audio.example/input.wav", {})

    assert requests[0] == ("GET", "/v1/models?include_outdated=true", None)
    assert [model["type"] for model in models] == ["transcription", "tts"]
    assert requests[-1] == (
        "POST",
        "/v1/listen?model=nova-live",
        {"url": "https://audio.example/input.wav"},
    )
    assert transcript == {"text": "live transcript"}

    captured = {}
    monkeypatch.setattr(
        provider,
        "_request",
        lambda method, path, body=None, **kwargs: captured.update({"method": method, "path": path, "body": body, **kwargs}) or b"audio",
    )
    response = provider.tts("deepgram/aura-live", "hello", None)

    assert captured == {
        "method": "POST",
        "path": "/v1/speak?model=aura-live",
        "body": {"text": "hello"},
        "accept": "audio/mpeg",
    }
    assert response["audio"].startswith("data:audio/mpeg;base64,")


def test_databricks_discovers_workspace_serving_endpoints_and_invokes_selected_endpoint(monkeypatch):
    import json

    from domain.ai_client.providers import detect_available_providers
    from domain.ai_client.providers.databricks_model_serving_provider import DatabricksModelServingProvider

    monkeypatch.setenv("DATABRICKS_TOKEN", "databricks-token")
    monkeypatch.setenv("DATABRICKS_HOST", "https://workspace.cloud.databricks.com")
    seen = []

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

    def fake_urlopen(request, **_kwargs):
        seen.append((request.method, request.full_url, request.headers.get("Authorization"), request.data))
        if request.method == "GET":
            return Response(
                {
                    "endpoints": [
                        {
                            "name": "chat-endpoint",
                            "state": {"ready": "READY"},
                            "config": {"served_entities": [{"name": "catalog.schema.chat-model"}]},
                        },
                        {
                            "name": "embedding-endpoint",
                            "state": {"ready": "READY"},
                            "config": {"served_entities": [{"name": "bge-embedding-model"}]},
                        },
                    ]
                }
            )
        return Response({"choices": [{"message": {"content": "workspace reply"}, "finish_reason": "stop"}]})

    monkeypatch.setattr(
        "domain.ai_client.providers.databricks_model_serving_provider.urllib.request.urlopen",
        fake_urlopen,
    )
    provider = DatabricksModelServingProvider()
    models = provider.list_models()
    assert [model["model_id"] for model in models] == ["chat-endpoint", "embedding-endpoint"]
    assert models[0]["metadata"]["ready"] is True
    assert models[1]["type"] == "embedding"
    response = provider.complete("databricks-model-serving/chat-endpoint", [{"role": "user", "content": "Hi"}], [], {})
    assert response["content"][0]["text"] == "workspace reply"
    assert seen[0][:3] == (
        "GET",
        "https://workspace.cloud.databricks.com/api/2.0/serving-endpoints",
        "Bearer databricks-token",
    )
    assert seen[1][1].endswith("/serving-endpoints/chat-endpoint/invocations")
    assert isinstance(detect_available_providers()["databricks-model-serving"], DatabricksModelServingProvider)


def test_azure_openai_discovers_live_deployments_and_routes_chat_and_embeddings(monkeypatch):
    import json

    from domain.ai_client.providers.azure_openai_provider import AzureOpenAIProvider

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://resource.openai.azure.com")
    seen = []

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

    def fake_urlopen(request, **_kwargs):
        seen.append((request.method, request.full_url, request.headers.get("Api-key"), request.data))
        if request.method == "GET":
            return Response(
                {
                    "data": [
                        {"id": "chat-deployment", "model": {"name": "gpt-live", "version": "1"}},
                        {"id": "embedding-deployment", "model": {"name": "text-embedding-live", "version": "2"}},
                    ]
                }
            )
        if "/embeddings?" in request.full_url:
            return Response({"data": [{"embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 2, "total_tokens": 2}})
        return Response({"choices": [{"message": {"content": "azure reply"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("domain.ai_client.providers.azure_openai_provider.urllib.request.urlopen", fake_urlopen)
    provider = AzureOpenAIProvider()
    models = provider.list_models()
    assert [model["model_id"] for model in models] == ["chat-deployment", "embedding-deployment"]
    assert models[1]["type"] == "embedding"
    answer = provider.complete("azure-openai/chat-deployment", [{"role": "user", "content": "Hi"}], [], {})
    embeddings = provider.embed("azure-openai/embedding-deployment", "hello")
    assert answer["content"][0]["text"] == "azure reply"
    assert embeddings == {"embeddings": [[0.1, 0.2]], "usage": {"input_tokens": 2, "total_tokens": 2}}
    assert seen[0][:3] == (
        "GET",
        "https://resource.openai.azure.com/openai/deployments?api-version=2024-10-21",
        "azure-key",
    )
    assert "/deployments/chat-deployment/chat/completions?" in seen[1][1]
    assert "/deployments/embedding-deployment/embeddings?" in seen[2][1]


def test_replicate_uses_paginated_live_models_and_runs_the_latest_live_version(monkeypatch):
    from domain.ai_client.providers.replicate_provider import ReplicateProvider

    pages = {
        "models": {
            "results": [{"owner": "owner", "name": "first", "latest_version": {"id": "version-a"}, "default_example": {"input": {"prompt": "old"}}}],
            "next": "https://replicate.example/v1/models?cursor=two",
        },
        "https://replicate.example/v1/models?cursor=two": {
            "results": [{"owner": "owner", "name": "second", "latest_version": {"id": "version-b"}, "default_example": {"input": {"text": "old"}}}],
            "next": None,
        },
    }
    monkeypatch.setenv("REPLICATE_API_TOKEN", "test-replicate-token")
    ReplicateProvider._INVENTORY_CACHE.clear()
    provider = ReplicateProvider()
    calls = []

    def fake_request(method, path, body=None, **_kwargs):
        calls.append((method, path, body))
        if method == "GET":
            return pages[path]
        return {"id": "prediction", "status": "succeeded", "output": "live output"}

    monkeypatch.setattr(provider, "_request_json", fake_request)
    models = provider.list_models()
    response = provider.complete("owner/second", [{"role": "user", "content": "new prompt"}], [], {})

    assert [model["model_id"] for model in models] == ["owner/first", "owner/second"]
    assert all(model["metadata"]["source"] == "native_models_endpoint" for model in models)
    assert calls[-1] == ("POST", "predictions", {"version": "owner/second:version-b", "input": {"text": "new prompt"}})
    assert response["content"] == [{"type": "text", "text": "live output"}]

    image = provider.image_gen("owner/first", "draw this", {})

    assert calls[-1] == ("POST", "predictions", {"version": "owner/first:version-a", "input": {"prompt": "draw this"}})
    assert image["images"] == ["live output"]


def test_litellm_proxy_discovers_every_model_served_by_the_configured_gateway():
    from domain.ai_client.providers import _openai_compatible_spec_manifest
    from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider
    from domain.ai_client.providers.provider_catalog import OPENAI_COMPATIBLE_PROVIDER_SPECS

    spec = OPENAI_COMPATIBLE_PROVIDER_SPECS["litellm-proxy"]
    provider = OpenAICompatibleProvider.from_manifest(_openai_compatible_spec_manifest(spec))

    assert spec["curated_models"] == []
    assert provider._base_url == "http://127.0.0.1:4000/v1"
    assert provider._remote_model_list_path == "/models"


def test_saved_litellm_connection_endpoint_overrides_the_builtin_default(monkeypatch):
    import domain.ai_client.providers as providers

    monkeypatch.setattr(providers, "list_custom_providers", lambda: [])
    monkeypatch.setattr(
        providers,
        "provider_named_api_keys",
        lambda provider_id="": [
            {
                "provider_id": "litellm-proxy",
                "api_id": "team",
                "configured": True,
                "kind": "llm",
                "base_url": "https://gateway.example/v1",
            }
        ] if provider_id in {"", "litellm-proxy"} else [],
    )

    manifest = providers._provider_manifest_map()["litellm-proxy"]

    assert manifest["adapter"] == "openai_compatible"
    assert manifest["default_base_url"] == "https://gateway.example/v1"
    assert manifest["models"] == []


def test_live_inventory_removes_stale_bundled_models_from_the_ui_catalog(monkeypatch):
    import ecosystem.defaultspack.backend.ai_client.provider_catalog as catalog

    class Client:
        def list_providers(self):
            return [{"provider_id": "openrouter"}]

        def list_models(self, provider=None):
            assert provider in {None, "openrouter"}
            return [{
                "id": "openrouter/account-visible-model",
                "qualified_model_id": "openrouter/account-visible-model",
                "provider_id": "openrouter",
                "model_id": "account-visible-model",
                "metadata": {"source": "openrouter_models_api"},
            }]

    monkeypatch.setattr(catalog, "_runtime_client", lambda: Client())
    monkeypatch.setattr(
        catalog,
        "get_all_known_models",
        lambda **_kwargs: [{
            "id": "openrouter/stale-bundled-model",
            "qualified_model_id": "openrouter/stale-bundled-model",
            "provider_id": "openrouter",
            "model_id": "stale-bundled-model",
            "metadata": {"source": "openrouter_curated_overlay"},
        }],
    )

    models = catalog.list_model_catalog("openrouter")

    assert [model["model_id"] for model in models] == ["account-visible-model"]


def test_vercel_live_inventory_replaces_its_static_overlay_and_keeps_media_task_types(monkeypatch):
    import ecosystem.defaultspack.backend.ai_client.provider_catalog as catalog
    from domain.ai_client.providers.vercel_ai_gateway_provider import VercelAIGatewayProvider

    provider = VercelAIGatewayProvider(known_models=[])
    image = provider._normalize_remote_model({"id": "fal/image", "type": "image", "output_modalities": ["image"]})
    video = provider._normalize_remote_model({"id": "fal/video", "type": "video", "output_modalities": ["video"]})

    assert image["type"] == "image_gen"
    assert image["capabilities"]["image_generation"] is True
    assert video["type"] == "video_gen"
    assert video["capabilities"]["video_generation"] is True

    class Client:
        def list_providers(self):
            return [{"provider_id": "vercel-ai-gateway"}]

        def list_models(self, provider=None):
            assert provider in {None, "vercel-ai-gateway"}
            return [{
                "id": "vercel-ai-gateway/account-visible-model",
                "qualified_model_id": "vercel-ai-gateway/account-visible-model",
                "provider_id": "vercel-ai-gateway",
                "model_id": "account-visible-model",
                "metadata": {"source": "vercel_ai_gateway_models_api"},
            }]

    monkeypatch.setattr(catalog, "_runtime_client", lambda: Client())
    monkeypatch.setattr(
        catalog,
        "get_all_known_models",
        lambda **_kwargs: [{
            "id": "vercel-ai-gateway/stale-bundled-model",
            "qualified_model_id": "vercel-ai-gateway/stale-bundled-model",
            "provider_id": "vercel-ai-gateway",
            "model_id": "stale-bundled-model",
        }],
    )

    models = catalog.list_model_catalog("vercel-ai-gateway")

    assert [model["model_id"] for model in models] == ["account-visible-model"]
