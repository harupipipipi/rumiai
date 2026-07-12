from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.gateway_policy import GATEWAY_IDS, gateway_inventory  # noqa: E402
from domain.ai_client.providers import get_provider_catalog_map  # noqa: E402
from domain.components.registry import get_domain_component_registry  # noqa: E402


def test_gateway_routes_keep_upstream_selection_separate():
    models = gateway_inventory("portkey-ai-gateway", configured_routes=[
        {"upstream_provider": "anthropic", "upstream_model": "claude-exact"},
        {"upstream_provider": "openai", "upstream_model": "claude-exact"},
    ])
    assert [item["provider_id"] for item in models] == ["portkey-ai-gateway"] * 2
    assert {item["metadata"]["upstream_provider"] for item in models} == {"anthropic", "openai"}
    assert {item["model_id"] for item in models} == {"anthropic/claude-exact", "openai/claude-exact"}


def test_observability_payload_is_not_treated_as_catalog():
    logs = {"data": [{"id": "seen-in-a-log", "litellm_provider": "openai"}]}
    assert gateway_inventory("helicone-gateway", proxy_models=logs) == []
    assert gateway_inventory("cloudflare-ai-gateway", proxy_models=logs) == []


def test_litellm_authenticated_proxy_models_are_inventory():
    models = gateway_inventory("litellm-proxy", proxy_models={"data": [
        {"id": "deployment-a", "litellm_provider": "azure"},
        {"id": "deployment-b"},
    ]})
    assert [item["model_id"] for item in models] == ["azure/deployment-a", "unknown/deployment-b"]
    assert all(item["metadata"]["source"] == "litellm_proxy_models_api" for item in models)


def test_gateway_routes_reject_secret_bearing_inventory():
    with pytest.raises(ValueError, match="secrets"):
        gateway_inventory("portkey-ai-gateway", configured_routes=[
            {"upstream_provider": "openai", "upstream_model": "gpt", "api_key": "secret"}
        ])


def test_gateway_matrix_registered_without_defaults():
    get_domain_component_registry(force_reload=True)
    assert GATEWAY_IDS <= set(get_provider_catalog_map())
    for provider_id in GATEWAY_IDS:
        payload = json.loads((DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(encoding="utf-8"))
        manifest = payload["provider_manifest"]
        assert "default_model" not in manifest
        assert manifest["config"]["observability_is_not_inventory"] is True
        assert manifest["config"]["upstream_selection_separate"] is True
