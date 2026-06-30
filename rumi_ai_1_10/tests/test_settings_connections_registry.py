from core_runtime.connections.registry import ConnectionsRegistry
from core_runtime.connections.oauth_service import InMemoryOAuthStateStore
from core_runtime.connections.providers.codex import CODEX_PROVIDER
from core_runtime.connections.providers.cloudflare import CLOUDFLARE_PROVIDER
from core_runtime.connections.providers.google import GOOGLE_PROVIDER


def test_connections_registry_orders_providers():
    registry = ConnectionsRegistry()
    registry.register(GOOGLE_PROVIDER)
    registry.register(CLOUDFLARE_PROVIDER)
    registry.register(CODEX_PROVIDER)
    providers = registry.list_providers()
    assert [provider["providerId"] for provider in providers][:3] == ["cloudflare", "google", "codex"]


def test_provider_safe_payload_has_no_secret():
    payload = CLOUDFLARE_PROVIDER.to_dict()
    assert "client_secret" not in str(payload).lower()
    assert payload["officialBrokerSupported"] is True
    assert payload["selfHostClientSupported"] is True
    assert payload["pkceSupported"] is True
    assert payload["capabilities"][0]["displayName"] == "Read account metadata"


def test_codex_provider_safe_payload_has_no_token_material():
    payload = CODEX_PROVIDER.to_dict()
    payload_text = str(payload).lower()
    assert "client_secret" not in payload_text
    assert "secret_value" not in payload_text
    assert "token_value" not in payload_text
    assert payload["providerId"] == "codex"
    assert payload["authType"] == "api_key"
    assert payload["officialBrokerSupported"] is False
    assert payload["selfHostClientSupported"] is False
    assert payload["metadata"]["credential_kind"] == "codex_access_token"
    assert payload["metadata"]["not_platform_api_key"] is True
    assert payload["metadata"]["not_workspace_agent_token"] is True


def test_codex_core_provider_exposes_high_risk_execution_capabilities():
    capabilities = {capability.id: capability.risk for capability in CODEX_PROVIDER.capabilities}
    assert capabilities["codex.access_token.configure"] == "high"
    assert capabilities["codex.app_server.connect"] == "high"
    assert capabilities["codex.thread.start"] == "medium"
    assert capabilities["codex.turn.run"] == "medium"
    assert capabilities["codex.events.stream"] == "medium"
    assert capabilities["codex.approval.respond"] == "high"
    assert capabilities["codex.exec.run"] == "high"


def test_oauth_state_store_expires_state():
    now = 1_000.0
    store = InMemoryOAuthStateStore(now=lambda: now)
    store.put("state", {"provider_id": "google"}, ttl_seconds=10)

    now = 1_011.0

    try:
        store.pop("state")
    except ValueError as exc:
        assert str(exc) == "Invalid or expired OAuth state"
    else:
        raise AssertionError("expired OAuth state should fail closed")
