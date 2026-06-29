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
    priority=30,
    oauth=OAuthConfig(
        authorization_url="https://dash.cloudflare.com/oauth2/auth",
        token_url="https://dash.cloudflare.com/oauth2/token",
        revoke_url="https://dash.cloudflare.com/oauth2/revoke",
        userinfo_url="https://dash.cloudflare.com/oauth2/userinfo",
        default_scopes=[],
        pkce_supported=True,
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
    metadata={
        "scope_selection": "Select exact OAuth scopes from Cloudflare OAuth client configuration/API for the minimum runner resources used by the implementation.",
        "oss_behavior": "If official broker is unavailable, show Download Official App and Configure self-host OAuth.",
    },
)
