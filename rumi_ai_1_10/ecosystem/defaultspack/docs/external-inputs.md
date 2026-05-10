# External Inputs

External inputs are messages that enter Rumi from systems outside the local UI:
webhooks, chat platforms, automation callbacks, tunnels, local scripts, or
future connectors. They all use the same framework boundary:

```text
provider payload
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> submit_input
  -> ResponsePlanner
  -> ResponseAdapter
```

The goal is to keep provider details at the edge. Chat, agent, and flow logic
should receive normalized input, not Slack, Discord, LINE, or tunnel-specific
payloads.

## Core Types

`ExternalEvent` is the normalized inbound record. It contains stable fields:
`provider`, `workspace`, `scope`, `actor`, `conversation`, `event`, `payload`,
`verified`, and redacted `metadata`. Provider-specific identifiers are absorbed
into those principals. Raw request bodies may be used for signature checks, but
raw secrets and token values are never exposed in the event object returned to
UI, logs, or docs.

`AudiencePolicy` decides whether an event is allowed to enter Rumi. Policy can
gate by provider, team, channel, user, mention style, direct message status,
rate limit, or required verification. Policy output is explicit: `allow`,
`ignore`, `deny`, or `needs_approval`.

`InputProfile` maps an allowed event to a `RumiInputEnvelope`: role, input text,
chat external key/title/model, source metadata, params, and tools. It performs
transformation only; it does not decide whether an event is allowed.

`submit_input` is the framework entrypoint after profile transformation. It
accepts a `RumiInputEnvelope`, persists the user message, and invokes the
chat-compatible turn runner.

`ResponsePlanner` converts the runtime result into a provider-neutral response
plan. It decides whether to reply, acknowledge only, defer, split, truncate, or
skip.

`ResponseAdapter` renders and delivers that plan through a provider-specific
surface such as a Slack thread, LINE reply token, Discord interaction response,
or generic webhook response.

## Event Contract

Example normalized event:

```json
{
  "provider": "line",
  "workspace": {
    "type": "line_destination",
    "id": "destination-id"
  },
  "scope": {
    "type": "group",
    "id": "C123"
  },
  "actor": {
    "type": "user",
    "id": "U123"
  },
  "conversation": {
    "type": "external",
    "id": "line:group:C123"
  },
  "event": {
    "id": "evt_01",
    "message_id": "msg_01",
    "type": "message",
    "message_type": "text"
  },
  "payload": {
    "type": "message"
  },
  "verified": true,
  "metadata": {
    "reply_token": "short-lived-provider-handle"
  }
}
```

Short-lived provider reply handles are kept in metadata for adapter use. They
must not be treated as long-lived configured tokens or displayed back to UI.

## Processing Rules

1. Verify the request before parsing trust-sensitive fields.
2. Normalize provider payloads into `ExternalEvent`.
3. Drop duplicates using `provider + event_id`.
4. Evaluate `AudiencePolicy`.
5. Select `InputProfile`.
6. Call `submit_input`.
7. Run `ResponsePlanner`.
8. Deliver through `ResponseAdapter`.

If any step rejects the event, the adapter should return the provider-expected
acknowledgement without creating a chat message.

## Local First Boundary

External input support does not make the local runtime public by default. The
gateway and HTTP transport bind to loopback unless configuration explicitly
allows otherwise. A public URL provider is just a replaceable edge component.
Cloudflare Quick Tunnel can be used during development, but it is not part of
the core architecture and must remain swappable with another tunnel, reverse
proxy, or platform ingress.

## Current Defaultspack Routes

Current integration routes are provider-specific adapters that should converge
on the framework boundary above:

| Route | Purpose |
|---|---|
| `POST /api/integrations/slack/events` | Slack Events API intake |
| `POST /api/integrations/line/webhook` | LINE Messaging API webhook intake |
| `POST /api/integrations/discord/interactions` | Discord interaction intake |
| `POST /api/integrations/discord/events` | Discord message event intake |
| `GET /api/integrations/secrets` | Secret status only |
| `POST /api/integrations/secrets` | Set or clear write-only secrets |
| `GET /api/external/tokens` | API-key-like external token status |
| `POST /api/external/tokens` | Upsert, rename, or delete named external tokens |
| `POST /api/webhooks/inbound/{webhook_id}` | Generic webhook intake |
| `GET /api/webhooks/endpoints` | List webhook endpoint configs |
