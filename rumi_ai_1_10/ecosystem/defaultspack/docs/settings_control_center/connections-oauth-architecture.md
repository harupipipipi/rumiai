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

## Cloudflare

Use cases:

- Connect user Cloudflare account.
- Provision Rumi runner resources.
- Show cloud continuation readiness.
- Support official broker and self-host OAuth.

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
