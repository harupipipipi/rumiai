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
from domain.ai_client.providers import (  # noqa: E402
    _instantiate_manifest_provider,
    get_provider_catalog_map,
)
from domain.ai_client.providers.gateway_providers import (  # noqa: E402
    CloudflareAIGatewayProvider,
    GatewayConfigurationError,
    HeliconeGatewayProvider,
    PortkeyGatewayProvider,
)
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


def _manifest(provider_id):
    payload = json.loads(
        (DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return payload["provider_manifest"]


def test_gateway_manifests_are_executable_and_keep_route_inventory_dynamic():
    for provider_id in GATEWAY_IDS - {"litellm-proxy"}:
        manifest = _manifest(provider_id)
        assert manifest["supports_invoke"] is True
        assert manifest["catalog_only"] is False
        assert manifest["entrypoint"].startswith(
            "domain.ai_client.providers.gateway_providers:"
        )
        snapshot = json.loads(
            (
                DEFAULTSPACK / "domain" / "providers" / provider_id / "models.json"
            ).read_text(encoding="utf-8")
        )
        assert snapshot["models"] == []
        assert snapshot["snapshot"]["observability_is_not_inventory"] is True


def test_gateway_entrypoints_instantiate_from_configured_routes(monkeypatch):
    routes = [
        {"upstream_provider": "openai", "upstream_model": "gpt-exact"}
    ]
    monkeypatch.setenv("RUMI_GATEWAY_ROUTES_JSON", json.dumps(routes))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-key")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-1")
    monkeypatch.setenv("CLOUDFLARE_AI_GATEWAY_ID", "gateway-1")
    expected = {
        "cloudflare-ai-gateway": CloudflareAIGatewayProvider,
        "helicone-gateway": HeliconeGatewayProvider,
        "portkey-ai-gateway": PortkeyGatewayProvider,
    }
    for provider_id, expected_type in expected.items():
        provider = _instantiate_manifest_provider(_manifest(provider_id))
        assert isinstance(provider, expected_type)
        assert provider.list_models()[0]["model_id"] == "openai/gpt-exact"


def _completion_response():
    return {
        "choices": [
            {"message": {"content": "gateway answer"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }


def test_cloudflare_uses_compat_endpoint_and_gateway_auth(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-1")
    monkeypatch.setenv("CLOUDFLARE_AI_GATEWAY_ID", "gateway-1")
    provider = CloudflareAIGatewayProvider(
        provider_id="cloudflare-ai-gateway",
        api_key="gateway-key",
        configured_routes=[
            {"upstream_provider": "openai", "upstream_model": "gpt-exact"}
        ],
    )
    captured = {}

    def request(path, body, **_kwargs):
        captured.update(path=path, body=body, headers=provider._headers())
        return _completion_response()

    provider._request_json = request
    result = provider.complete(
        "cloudflare-ai-gateway/openai/gpt-exact",
        [{"role": "user", "content": "hello"}],
        [],
        {},
    )
    assert result["content"][0]["text"] == "gateway answer"
    assert provider.BASE_URL.endswith("/account-1/gateway-1/compat")
    assert captured["body"]["model"] == "openai/gpt-exact"
    assert captured["headers"]["cf-aig-authorization"] == "Bearer gateway-key"


def test_portkey_and_helicone_compile_distinct_route_headers(monkeypatch):
    route = {"upstream_provider": "anthropic-provider", "upstream_model": "claude-exact"}
    portkey = PortkeyGatewayProvider(
        provider_id="portkey-ai-gateway",
        api_key="portkey-key",
        default_base_url="https://api.portkey.ai/v1",
        configured_routes=[route],
    )
    captured = {}

    def portkey_request(_path, body, **_kwargs):
        captured.update(body=body, headers=portkey._headers())
        return _completion_response()

    portkey._request_json = portkey_request
    portkey.complete("anthropic-provider/claude-exact", [], [], {})
    assert captured["body"]["model"] == "@anthropic-provider/claude-exact"
    assert captured["headers"]["x-portkey-api-key"] == "portkey-key"

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *_args: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    helicone_route = {
        **route,
        "target_url": "https://api.example.com/v1?ignored=true",
    }
    helicone = HeliconeGatewayProvider(
        provider_id="helicone-gateway",
        api_key="helicone-key",
        default_base_url="https://ai-gateway.helicone.ai/v1",
        configured_routes=[helicone_route],
    )
    helicone._active_route = helicone_route
    headers = helicone._headers()
    assert headers["Helicone-Auth"] == "Bearer helicone-key"
    assert headers["Helicone-Target-Url"] == "https://api.example.com/v1"
    assert headers["Helicone-Target-Provider"] == "anthropic-provider"


def test_helicone_target_policy_blocks_private_or_credentialed_hosts(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *_args: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    provider = HeliconeGatewayProvider(
        provider_id="helicone-gateway",
        api_key="test-key",
        default_base_url="https://ai-gateway.helicone.ai/v1",
        configured_routes=[
            {
                "upstream_provider": "custom",
                "upstream_model": "model",
                "target_url": "https://user:pass@example.com",
            }
        ],
    )
    provider._active_route = provider._configured_routes[0]
    with pytest.raises(GatewayConfigurationError):
        provider._headers()
