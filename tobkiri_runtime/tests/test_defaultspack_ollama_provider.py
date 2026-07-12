from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.ai_client.providers.ollama_provider import (  # noqa: E402
    OllamaAPIError,
    OllamaProvider,
)


TAGS = [
    {
        "name": "gemma4:latest",
        "model": "gemma4:latest",
        "modified_at": "2026-07-01T00:00:00Z",
        "size": 9_608_350_245,
        "digest": "digest-gemma4",
        "details": {
            "format": "gguf",
            "family": "gemma4",
            "families": ["gemma4"],
            "parameter_size": "8.0B",
            "quantization_level": "Q4_K_M",
        },
    },
    {
        "name": "nomic-embed-text:latest",
        "model": "nomic-embed-text:latest",
        "modified_at": "2026-07-02T00:00:00Z",
        "size": 274_000_000,
        "digest": "digest-nomic",
        "details": {
            "format": "gguf",
            "family": "nomic-bert",
            "families": ["nomic-bert"],
            "parameter_size": "137M",
            "quantization_level": "F16",
        },
    },
]

SHOW = {
    "gemma4:latest": {
        "parameters": "temperature 0.7\nnum_ctx 4096",
        "license": "test license",
        "template": "{{ .Prompt }}",
        "capabilities": ["completion", "vision", "tools", "thinking"],
        "details": {"family": "gemma4", "parameter_size": "8.0B"},
        "model_info": {
            "general.architecture": "gemma4",
            "gemma4.context_length": 131072,
        },
    },
    "nomic-embed-text:latest": {
        "capabilities": ["embedding"],
        "details": {"family": "nomic-bert", "parameter_size": "137M"},
        "model_info": {
            "general.architecture": "nomic-bert",
            "nomic-bert.context_length": 8192,
        },
    },
}

RUNNING = [
    {
        "name": "gemma4:latest",
        "model": "gemma4:latest",
        "digest": "digest-gemma4",
        "size": 6_591_830_464,
        "size_vram": 5_333_539_264,
        "expires_at": "2026-07-10T22:00:00Z",
        "context_length": 4096,
    }
]


def _provider(**kwargs):
    return OllamaProvider(
        base_url="http://127.0.0.1:11434/v1",
        server_base_url="http://127.0.0.1:11434",
        **kwargs,
    )


def _fake_native(path, *, body=None, timeout=None):
    del timeout
    if path == "/api/tags":
        return {"models": TAGS}
    if path == "/api/ps":
        return {"models": RUNNING}
    if path == "/api/show":
        return SHOW[str((body or {}).get("model"))]
    raise AssertionError(path)


def test_ollama_native_inventory_preserves_tags_types_capabilities_and_running_state():
    provider = _provider(detail_workers=2)
    with patch.object(provider, "_native_request_json", side_effect=_fake_native):
        models = provider._fetch_native_inventory([])

    assert [model["id"] for model in models] == [
        "ollama/gemma4:latest",
        "ollama/nomic-embed-text:latest",
    ]

    gemma = models[0]
    assert gemma["model_id"] == "gemma4:latest"
    assert gemma["type"] == "chat"
    assert gemma["context_window"] == 131072
    assert gemma["capabilities"]["image_input"] is True
    assert gemma["capabilities"]["tool_calling"] is True
    assert gemma["capabilities"]["thinking"] is True
    assert gemma["capabilities"]["json_schema"] is True
    assert gemma["metadata"]["digest"] == "digest-gemma4"
    assert gemma["metadata"]["running"] is True
    assert gemma["metadata"]["size_vram"] == 5_333_539_264
    assert gemma["metadata"]["active_context_length"] == 4096
    assert gemma["metadata"]["default_context_length"] == 4096
    assert gemma["metadata"]["quantization_level"] == "Q4_K_M"

    embedding = models[1]
    assert embedding["type"] == "embedding"
    assert embedding["context_window"] == 8192
    assert embedding["capabilities"]["text_input"] is True
    assert embedding["capabilities"]["text_output"] is False
    assert embedding["capabilities"]["streaming"] is False
    assert embedding["metadata"]["running"] is False
    assert embedding["metadata"]["load_state"] == "installed"


def test_ollama_detail_cache_is_reused_when_digest_is_unchanged():
    provider = _provider(detail_workers=2)
    with patch.object(provider, "_native_request_json", side_effect=_fake_native):
        previous = provider._fetch_native_inventory([])

    with patch.object(provider, "_native_request_json", side_effect=_fake_native), patch.object(
        provider,
        "_show_model",
    ) as show_model:
        refreshed = provider._fetch_native_inventory(previous)

    show_model.assert_not_called()
    assert [model["model_id"] for model in refreshed] == [
        "gemma4:latest",
        "nomic-embed-text:latest",
    ]
    assert refreshed[0]["metadata"]["catalog_cache_state"] == "fresh"


def test_ollama_url_normalization_no_auth_and_optional_proxy_auth(monkeypatch):
    for name in ("OLLAMA_BASE_URL", "OLLAMA_HOST", "OLLAMA_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    provider = OllamaProvider(base_url="localhost:11434")
    assert provider.BASE_URL == "http://localhost:11434/v1"
    assert provider._server_base_url() == "http://localhost:11434"
    assert "Authorization" not in provider._headers(content_type="")

    authenticated = OllamaProvider(
        api_key="proxy-token",
        base_url="https://ollama.example.test/custom/v1",
    )
    assert authenticated.BASE_URL == "https://ollama.example.test/custom/v1"
    assert authenticated._server_base_url() == "https://ollama.example.test/custom"
    assert authenticated._headers(content_type="")["Authorization"] == "Bearer proxy-token"


def test_ollama_cache_keeps_last_known_inventory_on_refresh_failure(tmp_path):
    provider = _provider(cache_ttl_seconds=60)
    cache_path = tmp_path / "ollama.models.json"

    with patch.object(provider, "_remote_model_cache_path", return_value=cache_path), patch.object(
        provider,
        "_native_request_json",
        side_effect=_fake_native,
    ):
        fresh = provider.refresh_models()

    assert len(fresh) == 2
    assert cache_path.exists()

    with patch.object(provider, "_remote_model_cache_path", return_value=cache_path), patch.object(
        provider,
        "_fetch_native_inventory",
        side_effect=OllamaAPIError("offline", kind="network_error"),
    ):
        stale = provider.refresh_models()

    assert len(stale) == 2
    assert all(model["metadata"]["catalog_cache_state"] == "stale" for model in stale)


def test_ollama_unload_is_explicit_keep_alive_zero():
    provider = _provider()
    calls = []

    def fake_request(path, *, body=None, timeout=None):
        calls.append((path, body, timeout))
        return {"done": True}

    with patch.object(provider, "_native_request_json", side_effect=fake_request):
        provider.unload_model("ollama/gemma4:latest")

    assert calls == [
        (
            "/api/generate",
            {"model": "gemma4:latest", "keep_alive": 0, "stream": False},
            None,
        )
    ]


def test_ollama_component_owns_runtime_inventory_and_registers_provider():
    from domain.ai_client.providers import detect_available_providers, get_provider_catalog_map
    from domain.components.registry import get_domain_component_registry

    component_manifest_path = DEFAULTSPACK_ROOT / "domain" / "providers" / "ollama" / "manifest.json"
    payload = json.loads(component_manifest_path.read_text(encoding="utf-8"))
    provider_manifest = payload["provider_manifest"]

    assert provider_manifest["adapter"] == "python_entrypoint"
    assert provider_manifest["entrypoint"].endswith("ollama_provider:OllamaProvider")
    assert provider_manifest["default_base_url"] == "local://ollama"
    assert provider_manifest["config"]["model_list_path"] == "/api/tags"
    assert provider_manifest["config"]["model_detail_path"] == "/api/show"
    assert provider_manifest["config"]["running_models_path"] == "/api/ps"
    assert "default_model" not in provider_manifest

    catalog_provider_dir = (
        ROOT
        / "ecosystem"
        / "rumi_model_catalog_pack"
        / "extensions"
        / "llm"
        / "providers"
        / "ollama"
    )
    assert not (catalog_provider_dir / "manifest.json").exists()
    assert not (catalog_provider_dir / "models" / "llama3.1-8b.json").exists()

    get_domain_component_registry(force_reload=True)
    entry = get_provider_catalog_map()["ollama"]
    assert entry["default_model"] == ""
    assert entry["availability"]["configuration_source"] == "builtin_local_provider"
    assert entry["availability"]["supports_invoke"] is True
    assert isinstance(detect_available_providers()["ollama"], OllamaProvider)
