# External Tokens

External input providers require secrets for verification and outbound replies.
Rumi treats these values as write-only credentials.

Raw token values must never be shown in UI, API responses, logs, audit records,
debug dumps, generated docs, or delivery status.

## Token Classes

| Class | Example | Use |
|---|---|---|
| Signing secret | Slack signing secret, LINE channel secret | Verify inbound webhooks |
| Public verification key | Discord public key | Verify inbound interactions |
| Outbound bot token | Slack bot token, Discord bot token, LINE channel access token | Send replies |
| Local intake token | Gateway bearer token or webhook shared token | Protect local intake |
| Reply handle | LINE reply token, Discord interaction id/token | Send short-lived response |

Reply handles are not long-lived credentials, but they still must be treated as
sensitive because they can authorize a response.

## Storage

External provider credentials should live in the Rumi secret store or process
environment. Code and profiles should reference secret names, not raw values.

The named external token API follows the same pattern as provider API keys:

| Endpoint | Behavior |
|---|---|
| `GET /api/external/tokens` | Returns provider token status, masked labels, kinds, and endpoint links |
| `POST /api/external/tokens` | `upsert`, `rename`, or `delete` a named token |

Named token secret keys use `RUMIEXT_{PROVIDER}_{TOKEN_ID}`. Metadata is stored
separately from the raw secret and includes provider id, token id, display name,
kind, scopes, endpoint ids, and timestamps.

The legacy integration secret API remains for compatibility:

| Endpoint | Behavior |
|---|---|
| `GET /api/integrations/secrets` | Returns provider status and configured key names only |
| `POST /api/integrations/secrets` | Sets or clears a supported secret value |

The write endpoint accepts a raw value because it is the intake path for saving
a secret. The response must not echo that value.

## Display Rules

Allowed:

```json
{
  "provider_id": "slack",
  "configured": true,
  "configured_keys": ["SLACK_SIGNING_SECRET", "SLACK_BOT_TOKEN"]
}
```

Not allowed:

```json
{
  "SLACK_BOT_TOKEN": "<raw-token-value>"
}
```

Never partially mask by showing prefixes or suffixes unless there is a concrete
operator need and the value cannot be used as a credential. Prefer stable key
names, hashes, creation time, and rotation status.

## Audit And Redaction

Audit records may include:

- secret name;
- provider id;
- actor;
- operation: set, clear, rotate, verify;
- success or failure;
- redacted error category.

Audit records must not include:

- token values;
- authorization headers;
- cookies;
- signing secret values;
- reply token values;
- full provider request bodies when they contain credentials.

## Rotation

Rotation should be supported without changing profiles:

1. Save the new secret under the same secret name.
2. Verify incoming signatures or outbound delivery.
3. Remove the old provider-side credential.
4. Record a redacted audit event.

Profiles should not need edits during rotation because they reference secret
names, not secret values.

## URL Providers Are Not Tokens

Tunnel or ingress URLs are configuration, not credentials, but they can still be
sensitive operational details. Cloudflare Quick Tunnel is only one possible URL
provider for development. The external input framework must work the same way
with any tunnel, reverse proxy, or hosted ingress.
