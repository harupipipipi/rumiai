from core_runtime.connections.registry import ConnectionsRegistry
from core_runtime.connections.providers.cloudflare import CLOUDFLARE_PROVIDER
from core_runtime.connections.providers.google import GOOGLE_PROVIDER


def test_connections_registry_orders_providers():
    registry = ConnectionsRegistry()
    registry.register(GOOGLE_PROVIDER)
    registry.register(CLOUDFLARE_PROVIDER)
    providers = registry.list_providers()
    assert [provider["providerId"] for provider in providers][:2] == ["cloudflare", "google"]


def test_provider_safe_payload_has_no_secret():
    payload = CLOUDFLARE_PROVIDER.to_dict()
    assert "client_secret" not in str(payload).lower()
    assert payload["officialBrokerSupported"] is True
    assert payload["selfHostClientSupported"] is True
    assert payload["pkceSupported"] is True
    assert payload["capabilities"][0]["displayName"] == "Read account metadata"
