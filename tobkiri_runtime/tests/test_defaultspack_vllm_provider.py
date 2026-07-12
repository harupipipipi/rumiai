from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.providers.vllm_provider import VLLMProvider  # noqa: E402


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_vllm_inventory_preserves_exact_served_aliases_adapters_and_tasks(monkeypatch):
    payload = {
        "object": "list",
        "data": [
            {"id": "public-alias", "object": "model", "owned_by": "vllm", "task": "generate"},
            {"id": "embed-v2", "object": "model", "task": "embed"},
            {"id": "tenant/lora-a", "root": "base/model", "parent": "base/model", "runner": "generate"},
        ],
    }
    requests = []

    def fake_urlopen(request, **_kwargs):
        requests.append(request)
        return _Response(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = VLLMProvider(base_url="[::1]:8000", api_key="proxy-token")
    models = provider.refresh_models()

    assert [model["model_id"] for model in models] == ["public-alias", "embed-v2", "tenant/lora-a"]
    assert models[0]["type"] == "chat"
    assert models[1]["type"] == "embedding"
    assert models[2]["metadata"]["adapter"] is True
    assert models[2]["metadata"]["root_model"] == "base/model"
    assert requests[0].full_url == "http://[::1]:8000/v1/models"
    assert requests[0].headers["Authorization"] == "Bearer proxy-token"


def test_vllm_unknown_task_stays_unknown(monkeypatch):
    monkeypatch.delenv("RUMI_VLLM_TASK", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"data": [{"id": "opaque-name"}]}))
    model = VLLMProvider().refresh_models()[0]
    assert model["type"] == "unknown"
    assert model["capabilities"]["streaming"] is None
    assert model["metadata"]["capability_confidence"] == "unknown"


def test_vllm_cache_is_endpoint_and_auth_scoped_without_secrets(tmp_path, monkeypatch):
    paths = {}

    def cache_path(self):
        path = tmp_path / f"{self._cache_scope()}.json"
        paths[self._cache_scope()] = path
        return path

    monkeypatch.setattr(VLLMProvider, "_inventory_cache_path", cache_path)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"data": [{"id": "served"}]}))
    first = VLLMProvider(base_url="http://one:8000", api_key="secret-one")
    second = VLLMProvider(base_url="http://one:8000", api_key="secret-two")
    third = VLLMProvider(base_url="http://two:8000", api_key="secret-one")
    first.refresh_models()
    second.refresh_models()
    third.refresh_models()
    assert len(paths) == 3
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in paths.values())
    assert "secret-one" not in serialized
    assert "secret-two" not in serialized


def test_vllm_last_known_good_and_connected_empty(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    monkeypatch.setattr(VLLMProvider, "_inventory_cache_path", lambda _self: path)
    provider = VLLMProvider(cache_ttl_seconds=10)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"data": [{"id": "live", "task": "generate"}]}))
    assert provider.refresh_models()[0]["model_id"] == "live"

    def offline(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    stale = provider.refresh_models()
    assert stale[0]["metadata"]["catalog_cache_state"] == "stale"
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"data": []}))
    assert provider.probe() == {"connected": True, "status": "connected_empty", "status_code": 200, "model_count": 0}


def test_vllm_inventory_never_scans_or_loads(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"data": []}))
    monkeypatch.setattr("pathlib.Path.rglob", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("disk scan")))
    assert VLLMProvider().refresh_models() == []


def test_vllm_component_registers_runtime_owner():
    from domain.ai_client.providers import (
        detect_available_providers,
        get_all_known_models,
        get_provider_catalog_map,
    )
    from domain.components.registry import get_domain_component_registry

    manifest = json.loads((DEFAULTSPACK / "domain" / "providers" / "vllm" / "manifest.json").read_text(encoding="utf-8"))
    runtime = manifest["provider_manifest"]
    assert runtime["entrypoint"].endswith("vllm_provider:VLLMProvider")
    assert runtime["default_base_url"] == "local://vllm"
    assert "default_model" not in runtime
    assert not (ROOT / "ecosystem" / "rumi_model_catalog_pack" / "extensions" / "llm" / "providers" / "vllm" / "manifest.json").exists()
    get_domain_component_registry(force_reload=True)
    assert get_provider_catalog_map()["vllm"]["default_model"] == ""
    assert get_all_known_models("vllm") == []
    assert isinstance(detect_available_providers()["vllm"], VLLMProvider)
