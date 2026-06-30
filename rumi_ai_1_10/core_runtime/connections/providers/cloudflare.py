from __future__ import annotations

from ..models import ConnectionProvider, OAuthConfig, ProviderCapability

CLOUDFLARE_PROVIDER = ConnectionProvider(
    provider_id="cloudflare",
    display_name="Cloudflare",
    description="Continue Rumi tasks in the user's own Cloudflare account when this computer is offline.",
    icon="cloudflare",
    service_kind="cloud",
    auth_type="oauth2",
    official_broker_supported=True,
    self_host_client_supported=True,
    auth_template="generic_oauth2_pkce",
    token_import_supported=True,
    priority=30,
    oauth=OAuthConfig(
        authorization_url="https://dash.cloudflare.com/oauth2/auth",
        token_url="https://dash.cloudflare.com/oauth2/token",
        revoke_url="https://dash.cloudflare.com/oauth2/revoke",
        userinfo_url="https://dash.cloudflare.com/oauth2/userinfo",
        default_scopes=[],
        pkce_supported=True,
        token_endpoint_auth_method="client_secret_post",
    ),
    capabilities=[
        ProviderCapability(
            id="cloudflare.account.read",
            display_name="Read account metadata",
            description="List/select the Cloudflare account Rumi should use.",
            risk="low",
        ),
        ProviderCapability(
            id="cloudflare.runner.deploy",
            display_name="Deploy Rumi runner",
            description="Create or update Rumi runner resources such as Worker, Workflow, D1, R2, Queue, and secrets.",
            risk="medium",
        ),
    ],
    scope_presets=[
        {"id": "account_read", "label": "Read account metadata", "scopes": ["account:read", "user:read"]},
    ],
    scope_to_capability=[
        {"scopes": ["account:read"], "capabilities": ["cloudflare.account.read"]},
        {
            "scopes": [
                "workers:write",
                "workers_scripts:edit",
                "d1:write",
                "r2:write",
                "queues:write",
                "workflows:write",
            ],
            "capabilities": ["cloudflare.runner.deploy"],
        },
    ],
    adapter={
        "python": "ecosystem.defaultspack.domain.connections.cloudflare:CloudflareConnectionAdapter",
        "sdk_optional": True,
    },
    metadata={
        "scope_selection": "Select exact OAuth scopes from Cloudflare OAuth client configuration/API for the minimum runner resources used by the implementation.",
        "oss_behavior": "If official broker is unavailable, show Download Official App and Configure self-host OAuth.",
        "self_host_env": [
            "RUMI_CLOUDFLARE_OAUTH_CLIENT_ID",
            "RUMI_CLOUDFLARE_OAUTH_SCOPES",
            "RUMI_CLOUDFLARE_OAUTH_REDIRECT_URI",
        ],
        "self_host_client_credential": "optional_env",
        "direct_token_env": [
            "RUMI_CLOUDFLARE_OAUTH_ACCESS_TOKEN",
            "RUMI_CLOUDFLARE_OAUTH_REFRESH_TOKEN",
        ],
    },
)
