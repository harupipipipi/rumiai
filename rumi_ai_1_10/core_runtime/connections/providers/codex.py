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
            id="codex.access_token.configure",
            display_name="Configure Codex access token",
            description="Store a Codex access token for local and programmatic workflow integrations. The token is not used for Codex App Server auth.",
            risk="high",
        ),
        ProviderCapability(
            id="codex.app_server.connect",
            display_name="Connect Codex App Server",
            description="Use Codex App Server as a Tools & MCP tool source and automation endpoint with separate App Server auth.",
            risk="high",
        ),
        ProviderCapability(
            id="codex.thread.start",
            display_name="Start Codex thread",
            description="Start a Codex thread through a local or App Server-backed transport.",
            risk="medium",
        ),
        ProviderCapability(
            id="codex.turn.run",
            display_name="Run Codex turn",
            description="Run a Codex turn against a configured thread.",
            risk="medium",
        ),
        ProviderCapability(
            id="codex.events.stream",
            display_name="Stream Codex events",
            description="Read event streams from a Codex session without granting approvals by itself.",
            risk="medium",
        ),
        ProviderCapability(
            id="codex.approval.respond",
            display_name="Respond to Codex approvals",
            description="Approve or deny high-impact Codex actions such as writes, terminal commands, and git operations.",
            risk="high",
        ),
        ProviderCapability(
            id="codex.exec.run",
            display_name="Run Codex execution",
            description="Run Codex-backed execution that can reach workspace, terminal, or git operations under approval policy.",
            risk="high",
        ),
    ],
    metadata={
        "credential_kind": "codex_access_token",
        "app_server_auth_kind": "codex_app_server_secret",
        "not_platform_api_key": True,
        "not_workspace_agent_token": True,
        "secret_handling": "Never expose the raw Codex token or Codex App Server secret in Settings payloads, logs, snapshots, repository files, or CLI arguments.",
    },
)
