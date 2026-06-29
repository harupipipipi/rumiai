from __future__ import annotations

from ..models import ConnectionProvider, ProviderCapability

CODEX_PROVIDER = ConnectionProvider(
    provider_id="codex",
    display_name="Codex",
    description="Connect a Codex local/programmatic workflow access token and optional Codex App Server endpoint.",
    icon="terminal",
    service_kind="dev",
    auth_type="api_key",
    official_broker_supported=False,
    self_host_client_supported=False,
    priority=50,
    capabilities=[
        ProviderCapability(
            id="codex.local_workflow.access",
            display_name="Codex local workflow access",
            description="Use a Codex access token for local and programmatic workflow integrations.",
            risk="medium",
        ),
        ProviderCapability(
            id="codex.app_server.tools",
            display_name="Codex App Server tools",
            description="Expose Codex App Server as a tool source and automation endpoint.",
            risk="medium",
        ),
    ],
    metadata={
        "credential_kind": "codex_access_token",
        "not_platform_api_key": True,
        "not_workspace_agent_token": True,
        "secret_handling": "Never return the token in UI status payloads, logs, or repo artifacts.",
    },
)
