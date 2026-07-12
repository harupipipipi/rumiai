from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.openai_compatible_connections import (  # noqa: E402
    delete_connection,
    list_connections,
    save_connection,
)
from domain.ai_client.providers.generic_openai_compatible_provider import (  # noqa: E402
    GenericOpenAICompatibleProvider,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _connection(connection_id="alpha", **updates):
    value = {
        "connection_id": connection_id,
        "label": connection_id.title(),
        "base_url": "https://example.test/v1",
        "auth_mode": "none",
        "manual_models": [],
        "model_list": {"enabled": False},
    }
    value.update(updates)
    return value


def test_connection_store_has_stable_ids_and_never_persists_secrets(tmp_path):
    saved = save_connection(_connection(manual_models=["exact/model:tag"]), pack_root=tmp_path)
    assert saved["connection_id"] == "alpha"
    assert list_connections(pack_root=tmp_path)[0]["manual_models"] == ["exact/model:tag"]
    serialized = (tmp_path / "user_data" / "shared" / "openai_compatible_connections.json").read_text(encoding="utf-8")
    assert "exact/model:tag" in serialized
    with pytest.raises(ValueError, match="secret"):
        save_connection({**_connection(), "api_key": "do-not-save"}, pack_root=tmp_path)
    assert delete_connection("alpha", pack_root=tmp_path) is True


def test_manual_inventory_keeps_unknown_capabilities_unknown():
    models = GenericOpenAICompatibleProvider(_connection(manual_models=["opaque-model"])).list_models()
    assert models[0]["id"] == "openai_compatible/alpha:opaque-model"
    assert models[0]["type"] == "unknown"
    assert models[0]["capabilities"]["streaming"] is None
    assert models[0]["metadata"]["capability_confidence"] == "unknown"


def test_configured_model_list_paginates_and_preserves_exact_ids(monkeypatch, tmp_path):
    requests = []

    def urlopen(request, **_kwargs):
        requests.append(request.full_url)
        if "after=page-2" in request.full_url:
            return _Response({"result": {"models": [{"id": "Case/Two:Q4"}], "next": None}})
        return _Response({"result": {"models": [{"id": "org/One"}], "next": "page-2"}})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr(GenericOpenAICompatibleProvider, "_remote_model_cache_path", lambda self: tmp_path / f"{self.connection_id}.json")
    provider = GenericOpenAICompatibleProvider(_connection(model_list={"enabled": True, "url": "https://catalog.test/models", "items_path": "result.models", "next_path": "result.next", "cursor_param": "after", "max_pages": 3}))
    assert [item["model_id"] for item in provider.list_models()] == ["org/One", "Case/Two:Q4"]
    assert requests == ["https://catalog.test/models", "https://catalog.test/models?after=page-2"]


def test_auth_modes_and_connection_cache_paths_are_isolated(monkeypatch):
    monkeypatch.setenv("ALPHA_KEY", "secret-alpha")
    bearer = GenericOpenAICompatibleProvider(_connection(api_key_env="ALPHA_KEY", auth_mode="bearer"))
    header = GenericOpenAICompatibleProvider(_connection("beta", api_key_env="ALPHA_KEY", auth_mode="api_key_header", auth_header="X-Token"))
    assert bearer._headers()["Authorization"] == "Bearer secret-alpha"
    assert header._headers()["X-Token"] == "secret-alpha"
    assert bearer._remote_model_cache_path() != header._remote_model_cache_path()
    assert "secret-alpha" not in str(bearer._remote_model_cache_path())


def test_component_removes_invented_generic_default():
    from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map
    from domain.components.registry import get_domain_component_registry

    get_domain_component_registry(force_reload=True)
    entry = get_provider_catalog_map()["openai_compatible"]
    assert entry["default_model"] == ""
    assert entry["availability"]["supports_invoke"] is True
    assert get_all_known_models("openai_compatible") == []
    assert not (ROOT / "ecosystem" / "rumi_model_catalog_pack" / "extensions" / "llm" / "providers" / "openai_compatible" / "manifest.json").exists()
