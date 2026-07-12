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
    get_provider_catalog_map,
)
from domain.components.registry import get_domain_component_registry  # noqa: E402


IDS = {
    "sglang", "huggingface-tgi", "localai", "jan", "text-generation-webui",
    "llamafile", "mlx-lm-server", "mlc-llm-server",
}


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"data":[{"id":"served-exact"}]}'


def _manifest(provider_id):
    payload = json.loads((DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(encoding="utf-8"))
    return payload["provider_manifest"]


def test_selfhosted_matrix_registered_without_static_models():
    get_domain_component_registry(force_reload=True)
    catalog = get_provider_catalog_map()
    assert IDS <= set(catalog)
    for provider_id in IDS:
        manifest = _manifest(provider_id)
        assert "default_model" not in manifest
        assert manifest["config"]["discovery_side_effects"] == "none"
        assert manifest["config"]["state_dimensions"] == ["installed", "served", "loaded", "healthy"]


def test_anonymous_local_discovery_records_honest_state(monkeypatch, tmp_path):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response())
    provider = _instantiate_manifest_provider(_manifest("localai"))
    monkeypatch.setattr(provider, "_remote_model_cache_path", lambda: tmp_path / "models.json")
    model = provider.list_models()[0]
    assert model["model_id"] == "served-exact"
    assert model["metadata"]["served_state"] == "served"
    assert model["metadata"]["installed_state"] == "unknown"
    assert model["metadata"]["loaded_state"] == "unknown"
    assert model["metadata"]["healthy_state"] == "unknown"


def test_cache_scope_isolated_by_endpoint_and_auth_without_leaking_secret(monkeypatch):
    first = _instantiate_manifest_provider(_manifest("localai"))
    second_manifest = dict(_manifest("localai"))
    second_manifest["default_base_url"] = "http://127.0.0.1:9090/v1"
    second = _instantiate_manifest_provider(second_manifest)
    assert first._remote_model_cache_path() != second._remote_model_cache_path()
    monkeypatch.setattr(first, "_api_key", "private-key")
    assert "private-key" not in str(first._remote_model_cache_path())
