from core_runtime.connections.registry import ConnectionsRegistry
from core_runtime.connections.oauth_service import InMemoryOAuthStateStore
from core_runtime.connections.permission_resolver import resolve_connection_permissions
from core_runtime.connections.providers.codex import CODEX_PROVIDER
from core_runtime.connections.providers.cloudflare import CLOUDFLARE_PROVIDER
from core_runtime.connections.providers.github import GITHUB_PROVIDER
from core_runtime.connections.providers.google import GOOGLE_PROVIDER


def test_connections_registry_orders_providers():
    registry = ConnectionsRegistry()
    registry.register(GOOGLE_PROVIDER)
    registry.register(CLOUDFLARE_PROVIDER)
    registry.register(GITHUB_PROVIDER)
    registry.register(CODEX_PROVIDER)
    providers = registry.list_providers()
    assert [provider["providerId"] for provider in providers][:4] == ["cloudflare", "google", "github", "codex"]


def test_provider_safe_payload_has_no_secret():
    payload = CLOUDFLARE_PROVIDER.to_dict()
    payload_text = str(payload).lower()
    assert "rumi_cloudflare_oauth_client_secret" not in payload_text
    assert "secret_value" not in payload_text
    assert "token_value" not in payload_text
    assert payload["officialBrokerSupported"] is True
    assert payload["selfHostClientSupported"] is True
    assert payload["pkceSupported"] is True
    assert payload["authTemplate"] == "generic_oauth2_pkce"
    assert payload["tokenImportSupported"] is True
    assert payload["scopeToCapability"][0]["capabilities"] == ["cloudflare.account.read"]
    assert payload["capabilities"][0]["displayName"] == "Read account metadata"


def test_cloudflare_pages_write_requires_approval():
    resolved = resolve_connection_permissions(
        CLOUDFLARE_PROVIDER,
        {
            "scopes": ["pages:write"],
            "requested_capabilities": [
                "cloudflare.pages.project.write",
                "cloudflare.pages.deployment.write",
            ],
        },
    )

    assert resolved.capabilities == []
    assert resolved.approval_required_capabilities == [
        "cloudflare.pages.deployment.write",
        "cloudflare.pages.project.write",
    ]
    assert resolved.rejected_capabilities == []


def test_cloudflare_pages_write_does_not_grant_runner_deploy():
    resolved = resolve_connection_permissions(
        CLOUDFLARE_PROVIDER,
        {
            "scopes": ["pages:write"],
            "requested_capabilities": ["cloudflare.runner.deploy"],
        },
    )

    assert "cloudflare.runner.deploy" not in resolved.capabilities
    assert "cloudflare.runner.deploy" not in resolved.approval_required_capabilities
    assert "cloudflare.runner.deploy" in resolved.rejected_capabilities


def test_cloudflare_full_runner_scope_requires_approval_for_runner_deploy():
    resolved = resolve_connection_permissions(
        CLOUDFLARE_PROVIDER,
        {
            "scopes": [
                "workers:write",
                "workers_scripts:edit",
                "pages:write",
                "d1:write",
                "r2:write",
                "queues:write",
                "workflows:write",
            ],
            "requested_capabilities": ["cloudflare.runner.deploy"],
        },
    )

    assert resolved.capabilities == []
    assert resolved.approval_required_capabilities == ["cloudflare.runner.deploy"]
    assert resolved.rejected_capabilities == []


def test_codex_provider_safe_payload_has_no_token_material():
    payload = CODEX_PROVIDER.to_dict()
    payload_text = str(payload).lower()
    assert "client_secret" not in payload_text
    assert "secret_value" not in payload_text
    assert "token_value" not in payload_text
    assert payload["providerId"] == "codex"
    assert payload["authType"] == "codex"
    assert [method["id"] for method in payload["authMethods"]] == [
        "chatgpt_account",
        "codex_access_token",
        "app_server_secret",
    ]
    assert payload["officialBrokerSupported"] is False
    assert payload["selfHostClientSupported"] is False
    assert payload["metadata"]["credential_kind"] == "codex_access_token"
    assert payload["metadata"]["provider_kind"] == "codex"
    assert payload["metadata"]["platform_api_key_required"] is False
    assert payload["metadata"]["not_platform_api_key"] is True
    assert payload["metadata"]["not_workspace_agent_token"] is True
    assert payload["authTemplate"] == "credential_bundle"
    assert payload["tokenImportSupported"] is True
    assert payload["scopeToCapability"][0]["credential_kind"] == "codex_access_token"


def test_github_provider_template_supports_manifest_driven_import():
    payload = GITHUB_PROVIDER.to_dict()
    payload_text = str(payload).lower()
    assert "access_token_value" not in payload_text
    assert "refresh_token" not in payload_text
    assert "secret_value" not in payload_text
    assert payload["providerId"] == "github"
    assert payload["authTemplate"] == "generic_oauth2_pkce"
    assert payload["tokenImportSupported"] is True
    assert payload["scopeToCapability"][0]["capabilities"] == ["github.user.read"]


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
