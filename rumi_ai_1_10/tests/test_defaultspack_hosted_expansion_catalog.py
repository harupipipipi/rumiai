from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.providers import get_provider_catalog_map  # noqa: E402
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
        assert manifest["catalog_only"] is True
        assert manifest["supports_invoke"] is False


def test_native_task_adapters_are_not_misrepresented_as_openai_chat():
    native = {"cloudflare-workers-ai", "cohere", "jina-ai", "replicate", "voyage-ai"}
    for provider_id in native:
        manifest = _payload(provider_id)["provider_manifest"]
        assert manifest["adapter"] != "openai_compatible"
