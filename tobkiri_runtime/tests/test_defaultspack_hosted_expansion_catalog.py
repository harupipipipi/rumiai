from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.providers import (  # noqa: E402
    _instantiate_manifest_provider,
    get_all_known_models,
    get_provider_catalog_map,
)
from domain.ai_client.providers.hosted_native_providers import (  # noqa: E402
    CloudflareWorkersAIProvider,
    CohereProvider,
    JinaProvider,
    ReplicateProvider,
    VoyageProvider,
)
from domain.components.registry import get_domain_component_registry  # noqa: E402


EXPECTED = {
    "ai21": {"chat"},
    "alibaba-dashscope": {"chat", "embedding", "image"},
    "baidu-qianfan": {"chat", "embedding"},
    "cloudflare-workers-ai": {"chat", "embedding", "rerank", "image", "stt", "tts"},
    "cohere": {"chat", "embedding", "rerank"},
    "github-models": {"chat", "embedding"},
    "huggingface-inference": {"chat", "embedding", "image", "stt", "tts"},
    "jina-ai": {"embedding", "rerank"},
    "replicate": {"image", "video", "audio", "chat"},
    "siliconflow": {"chat", "embedding", "rerank", "image"},
    "tencent-hunyuan": {"chat", "embedding", "image"},
    "voyage-ai": {"embedding", "rerank"},
}


def _payload(provider_id):
    return json.loads((DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(encoding="utf-8"))


def test_hosted_expansion_is_complete_and_task_typed():
    get_domain_component_registry(force_reload=True)
    assert set(EXPECTED) <= set(get_provider_catalog_map())
    for provider_id, tasks in EXPECTED.items():
        payload = _payload(provider_id)
        manifest = payload["provider_manifest"]
        assert set(manifest["config"]["task_types"]) == tasks
        assert "default_model" not in manifest
        assert manifest["config"]["source_docs"].startswith("https://")


def test_embedding_and_rerank_only_providers_are_not_chat_providers():
    for provider_id in ("jina-ai", "voyage-ai"):
        manifest = _payload(provider_id)["provider_manifest"]
        assert "chat" not in manifest["config"]["task_types"]
        assert manifest["catalog_only"] is False
        assert manifest["supports_invoke"] is True


def test_native_task_adapters_are_not_misrepresented_as_openai_chat():
    native = {"cloudflare-workers-ai", "cohere", "jina-ai", "replicate", "voyage-ai"}
    for provider_id in native:
        manifest = _payload(provider_id)["provider_manifest"]
        assert manifest["adapter"] != "openai_compatible"
        assert manifest["entrypoint"].startswith(
            "domain.ai_client.providers.hosted_native_providers:"
        )


def test_native_hosted_snapshots_join_the_unified_typed_catalog():
    get_domain_component_registry(force_reload=True)
    native = {"cloudflare-workers-ai", "cohere", "jina-ai", "replicate", "voyage-ai"}
    models = [model for model in get_all_known_models() if model.get("provider_id") in native]
    assert len(models) == 18
    assert {model["type"] for model in models} == {
        "chat",
        "embedding",
        "rerank",
        "image",
        "video",
        "audio",
        "transcription",
        "tts",
    }
    assert all(model["supports_invoke"] is True for model in models)


class _Response:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


class _Opener:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []

    def __call__(self, request, **_kwargs):
        self.requests.append(request)
        return _Response(self.payloads.pop(0))


def _native(provider_id, monkeypatch, opener):
    envs = {
        "cohere": ("COHERE_API_KEY",),
        "cloudflare-workers-ai": ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"),
        "jina-ai": ("JINA_API_KEY",),
        "replicate": ("REPLICATE_API_TOKEN",),
        "voyage-ai": ("VOYAGE_API_KEY",),
    }
    for env in envs[provider_id]:
        monkeypatch.setenv(env, "account-1" if env.endswith("ACCOUNT_ID") else "test-key")
    provider = _instantiate_manifest_provider(_payload(provider_id)["provider_manifest"])
    provider._opener = opener
    return provider


def test_native_entrypoints_instantiate_from_trusted_manifests(monkeypatch):
    get_domain_component_registry(force_reload=True)
    expected = {
        "cohere": CohereProvider,
        "cloudflare-workers-ai": CloudflareWorkersAIProvider,
        "jina-ai": JinaProvider,
        "replicate": ReplicateProvider,
        "voyage-ai": VoyageProvider,
    }
    for provider_id, provider_type in expected.items():
        provider = _native(provider_id, monkeypatch, _Opener({}))
        assert isinstance(provider, provider_type)
        assert provider.list_models()


def test_cohere_native_chat_embed_rerank_and_inventory(monkeypatch):
    opener = _Opener(
        {
            "message": {"content": [{"type": "text", "text": "hello"}]},
            "finish_reason": "COMPLETE",
            "usage": {"billed_units": {"input_tokens": 2, "output_tokens": 1}},
        },
        {"embeddings": {"float": [[0.1, 0.2]]}, "meta": {}},
        {"results": [{"index": 0, "relevance_score": 0.9}]},
        {
            "models": [
                {"name": "command-a-plus-05-2026", "endpoints": ["chat"]},
                {"name": "embed-v4.0", "endpoints": ["embed"]},
            ],
            "next_page_token": "next",
        },
        {"models": [{"name": "rerank-v4.0-pro", "endpoints": ["rerank"]}]},
    )
    provider = _native("cohere", monkeypatch, opener)
    assert provider.complete("cohere/command-a-plus-05-2026", [{"role": "user", "content": "hi"}], [], {})["content"][0]["text"] == "hello"
    assert provider.embed("cohere/embed-v4.0", "document")["embeddings"] == [[0.1, 0.2]]
    assert provider.rerank("cohere/rerank-v4.0-pro", "q", ["d"])["results"][0]["index"] == 0
    assert {model["type"] for model in provider.list_models(refresh=True)} == {"chat", "embedding", "rerank"}
    assert opener.requests[0].full_url == "https://api.cohere.com/v2/chat"
    assert "page_token=next" in opener.requests[-1].full_url


def test_workers_ai_inventory_is_account_scoped_and_paginated(monkeypatch):
    opener = _Opener(
        {"success": True, "result": {"response": "done"}},
        {
            "result": [{"name": "@cf/meta/model-a", "task": {"name": "chat"}}],
            "result_info": {"total_pages": 2},
        },
        {
            "result": [{"name": "@cf/baai/embed-b", "task": {"name": "embedding"}}],
            "result_info": {"total_pages": 2},
        },
    )
    provider = _native("cloudflare-workers-ai", monkeypatch, opener)
    response = provider.complete("@cf/meta/model-a", [{"role": "user", "content": "hi"}], [], {})
    assert response["content"][0]["text"] == "done"
    assert "/accounts/account-1/ai/run/@cf/meta/model-a" in opener.requests[0].full_url
    models = provider.list_models(refresh=True)
    assert [model["model_id"] for model in models] == ["@cf/meta/model-a", "@cf/baai/embed-b"]
    assert "page=2" in opener.requests[-1].full_url


def test_jina_voyage_and_replicate_use_native_task_endpoints(monkeypatch):
    jina_open = _Opener({"data": [{"embedding": [0.3]}]}, {"results": [{"index": 0}]})
    jina = _native("jina-ai", monkeypatch, jina_open)
    assert jina.embed("jina-embeddings-v4", "x")["embeddings"] == [[0.3]]
    assert jina.rerank("jina-reranker-v3", "q", ["d"])["results"] == [{"index": 0}]
    assert jina_open.requests[1].full_url.endswith("/v1/rerank")

    voyage_open = _Opener({"data": [{"embedding": [0.4]}]}, {"data": [{"index": 0}]})
    voyage = _native("voyage-ai", monkeypatch, voyage_open)
    assert voyage.embed("voyage-4-large", "x")["embeddings"] == [[0.4]]
    assert voyage.rerank("rerank-2.5", "q", ["d"])["results"] == [{"index": 0}]

    replicate_open = _Opener({"status": "succeeded", "output": ["https://example.test/image.png"]})
    replicate = _native("replicate", monkeypatch, replicate_open)
    result = replicate.image_gen("black-forest-labs/flux-1.1-pro", "mountains", {})
    assert result["images"] == ["https://example.test/image.png"]
    assert replicate_open.requests[0].full_url.endswith(
        "/v1/models/black-forest-labs/flux-1.1-pro/predictions"
    )
