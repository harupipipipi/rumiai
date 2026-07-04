# Connections and OAuth Architecture

## Concept model

```txt
Provider
  Google / Cloudflare / GitHub / Slack

Connection
  A user's connected account for a provider.
  Example: google:haru@example.com

Credential
  Secret material such as access token, refresh token, API key.
  Stored encrypted through CredentialStore.

Capability
  What the connection allows.
  Example: drive.file.read, gmail.search, cloudflare.runner.deploy

Tool
  A callable Rumi action.
  Example: drive.search_files, gmail.search_messages
```

These are not interchangeable. Mixing them is how Settings becomes a spaghetti graph wearing a cardigan.

## Responsibility layers

Connections and OAuth are intentionally split into three layers:

1. **Core abstraction**: `core_runtime/connections/` defines provider, capability, credential, registry, and OAuth service primitives. It knows how to describe a provider and validate OAuth state lifetimes, but it does not decide which defaultspack routes, settings sections, or local token files are active.
2. **Defaultspack provider implementation**: `ecosystem/defaultspack/config/settings_control_center/providers/*.connection.json` and the defaultspack OAuth registry decide which providers appear in Settings, what scopes/services are available, and whether a provider is backed by the local runtime or by an official hosted app flow.
3. **Local/self-host token lifecycle**: `ecosystem/defaultspack/domain/ai_client/oauth_store.py` owns the local OAuth client config, PKCE start/callback flow, pending state TTL cleanup, encrypted token storage, metadata returned to Settings, and self-host-only connect/clear/disconnect actions.

The UI should read provider status and scope modes from the defaultspack registry/status payload. It should not infer scopes from button labels or make a provider appear connectable when the current runtime says the official app or self-host OAuth setup is required.

## Official app mode

Used by Rumi hosted/official app.

- Rumi owns provider OAuth clients.
- Client secret is stored only in Rumi hosted backend secret storage.
- User clicks Connect and sees browser authorization.
- The repo never contains official client secret.

## OSS/self-host mode

Used when the repo is cloned and run independently.

- Settings shows `Download Official App` for hosted OAuth broker features.
- Settings also shows `Configure self-host OAuth`.
- Self-host admin supplies their own OAuth client id/secret or PKCE client config.
- Desktop/CLI/public clients use PKCE.

## Required routes

```txt
GET  /api/connections/providers
GET  /api/connections
GET  /api/connections/:connection_id
POST /api/connections/:provider_id/start
GET  /api/connections/oauth/callback/:provider_id
POST /api/connections/:connection_id/refresh
POST /api/connections/:connection_id/revoke
DELETE /api/connections/:connection_id
```

## Token handling

- `access_token` and `refresh_token` never appear in UI payloads.
- Tokens are never logged.
- Tokens are encrypted at rest.
- Credential records use `credential_ref`, not raw values.
- Scope/capability display uses metadata, not token introspection text.

## Codex credential boundary

Codex has two separate settings concepts:

- **Codex access token** is an `accounts_connections` credential for local and programmatic Codex workflows. It is read from `RUMI_CODEX_ACCESS_TOKEN`, `CODEX_ACCESS_TOKEN`, or the local secret store and must never be sent to Codex App Server endpoints.
- **Codex App Server** is a `tools_mcp` tool source and automation endpoint. It can expose coding-thread, event-stream, approval, and execution capabilities through transports such as `stdio`, `unix`, `websocket_loopback`, and `websocket_remote`.
- **Codex App Server auth secret** is separate from the Codex access token. Remote or otherwise non-loopback App Server endpoints require `RUMI_CODEX_APP_SERVER_WS_TOKEN`, `RUMI_CODEX_APP_SERVER_SHARED_SECRET`, or matching `*_FILE` paths.
- **Codex action approvals** belong to Tools & MCP permission policy, not Accounts & Connections login state.
- **Codex automation readiness** belongs in the Computer & Automation summary because it describes whether high-impact automation can actually run.

## Cloudflare

Use cases:

- Connect user Cloudflare account.
- Provision Rumi runner resources.
- Show cloud continuation readiness.
- Support official broker and self-host OAuth.

Status payloads include `provisioning.status`, `resources`,
`last_deployed_at`, and redacted `last_error`. Expected states are:

```txt
sdk_missing
missing_token
missing_account_id
insufficient_capabilities
ready
deployed
degraded
error
```

`cloudflare_plan` and `cloudflare_dry_run` return the resource plan without
writes. `cloudflare_deploy` and `cloudflare_delete` require the
`cloudflare.runner.deploy` capability plus a local approval context; client
payload flags are not treated as authorization. Created resources are one
prefix-scoped Worker, D1 database, R2 bucket, Queue, and Workflow when
Workflows are available. Teardown only removes stored or prefix-owned resources.

Self-host setup may import a token or use env:

```env
CLOUDFLARE_API_TOKEN=
CF_API_TOKEN=
RUMI_CLOUDFLARE_OAUTH_ACCESS_TOKEN=
RUMI_CLOUDFLARE_OAUTH_REFRESH_TOKEN=
RUMI_CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_ACCOUNT_ID=
RUMI_CLOUDFLARE_ZONE_ID=
CLOUDFLARE_ZONE_ID=
RUMI_CLOUDFLARE_RUNNER_PREFIX=
RUMI_CLOUDFLARE_RUNNER_ENV=production
```

Install the optional Python SDK with `python -m pip install cloudflare` for SDK
paths. The adapter falls back to Cloudflare REST routes for runner resources
when generated SDK paths are unavailable. Recommended token permissions are
read-only account/resource permissions for status, and least-privilege Workers
Scripts, D1, R2, Queues, and Workflows write permissions for runner deployment.
Tokens and Worker secret values must never appear in Settings payloads.

## Google

Use cases:

- Connect Google account.
- Enable Gmail and Drive capabilities selectively.
- Request narrow scopes first.
- Show verification/restricted-scope warnings when needed.

## UI states

```txt
connected
not_connected
needs_official_app
missing_self_host_config
expired
error
requires_profile_binding
```
