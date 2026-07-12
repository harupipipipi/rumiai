from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.providers.llamacpp_provider import LlamaCppProvider  # noqa: E402


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_llamacpp_single_model_merges_props_without_mutation(monkeypatch):
    calls = []

    def urlopen(request, **_kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith("/models") and not request.full_url.endswith("/v1/models"):
            raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)
        if request.full_url.endswith("/v1/models"):
            return _Response({"data": [{"id": "C:\\models\\Qwen.GGUF", "meta": {"n_ctx_train": 8192, "n_params": 7}}]})
        return _Response({"default_generation_settings": {"n_ctx": 4096}, "chat_template": "template", "chat_template_caps": {"supports_tools": True}, "modalities": {"vision": True}})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    model = LlamaCppProvider(base_url="localhost:8080").refresh_models()[0]
    assert model["model_id"] == "C:\\models\\Qwen.GGUF"
    assert model["context_window"] == 4096
    assert model["capabilities"]["tool_calling"] is True
    assert model["capabilities"]["image_input"] is True
    assert calls == ["http://localhost:8080/models", "http://localhost:8080/v1/models", "http://localhost:8080/props"]
    assert all("load" not in url and "reload" not in url for url in calls)


def test_llamacpp_router_inventory_preserves_state_and_modalities(monkeypatch):
    payload = {"data": [{"id": "org/model:Q4", "path": "D:\\models\\model.gguf", "status": {"value": "sleeping"}, "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}}]}
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response(payload))
    model = LlamaCppProvider().refresh_models()[0]
    assert model["metadata"]["server_mode"] == "router"
    assert model["metadata"]["load_state"] == "sleeping"
    assert model["capabilities"]["image_input"] is True


def test_llamacpp_router_props_explicitly_disables_autoload(monkeypatch):
    requests = []
    monkeypatch.setattr("urllib.request.urlopen", lambda request, **_kwargs: requests.append(request.full_url) or _Response({"is_sleeping": True}))
    assert LlamaCppProvider().model_props("org/model:Q4")["is_sleeping"] is True
    assert requests == ["http://127.0.0.1:8080/props?model=org%2Fmodel%3AQ4&autoload=false"]


def test_llamacpp_last_known_good_is_connection_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(LlamaCppProvider, "_cache_path", lambda self: tmp_path / f"{self._scope()}.json")
    provider = LlamaCppProvider(api_key="secret")
    monkeypatch.setattr(provider, "_fetch_models", lambda: provider._normalize_models([{"id": "one"}], router=True))
    assert provider.refresh_models()[0]["model_id"] == "one"
    monkeypatch.setattr(provider, "_fetch_models", lambda: (_ for _ in ()).throw(OSError("offline")))
    assert provider.refresh_models()[0]["metadata"]["catalog_cache_state"] == "stale"
    assert "secret" not in next(tmp_path.iterdir()).read_text(encoding="utf-8")


def test_llamacpp_health_loading_is_connected(monkeypatch):
    def loading(*_args, **_kwargs):
        raise urllib.error.HTTPError("health", 503, "loading", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", loading)
    assert LlamaCppProvider().probe() == {"connected": True, "status": "loading", "status_code": 503}


def test_llamacpp_component_is_canonical_owner():
    from domain.ai_client.providers import detect_available_providers, get_all_known_models, get_provider_catalog_map
    from domain.components.registry import get_domain_component_registry

    payload = json.loads((DEFAULTSPACK / "domain" / "providers" / "llamacpp" / "manifest.json").read_text(encoding="utf-8"))
    assert payload["provider_manifest"]["entrypoint"].endswith("llamacpp_provider:LlamaCppProvider")
    assert not (ROOT / "ecosystem" / "rumi_model_catalog_pack" / "extensions" / "llm" / "providers" / "llama_cpp" / "manifest.json").exists()
    get_domain_component_registry(force_reload=True)
    assert get_provider_catalog_map()["llamacpp"]["default_model"] == ""
    assert get_all_known_models("llamacpp") == []
    assert isinstance(detect_available_providers()["llamacpp"], LlamaCppProvider)
