# Webhooks

Webhooks are one transport for the external input framework. A webhook handler
authenticates a provider request, extracts an `ExternalEvent`, and then hands the
event to policy and profile selection. Webhook code should stay thin.

## Handler Shape

```text
HTTP request
  -> signature or token check
  -> provider parser
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> submit_input
  -> ResponsePlanner
  -> ResponseAdapter
```

Handlers should only do provider-specific work:

- verify signatures, timestamps, or shared tokens;
- answer provider challenge requests;
- map payload fields to `ExternalEvent`;
- return the provider-required acknowledgement shape;
- call the selected `ResponseAdapter`.

They should not decide model behavior, conversation memory strategy, prompt
selection, or agent routing. Those belong to `InputProfile`.

## Request Verification

Provider verification must happen before trusting payload fields.

| Provider | Verification |
|---|---|
| Slack | `x-slack-signature` and `x-slack-request-timestamp` |
| LINE | `x-line-signature` |
| Discord | `x-signature-ed25519` and `x-signature-timestamp` |
| Generic webhook | Bearer token, HMAC signature, or another configured verifier |

Unsigned development mode may exist for local testing, but production profiles
must require verification. Verification results can be recorded as booleans or
status strings. Raw signing secrets and inbound token values must never be
shown.

## Idempotency

Every webhook event should have a stable `event_id`. The framework should drop
duplicates using:

```text
dedupe_key = provider + ":" + event_id
```

If a provider does not supply an event id, the handler may derive one from a
timestamp plus message id, or from a hash of stable payload fields. Do not hash
raw secrets into IDs.

## Challenge And Ack Responses

Some providers require a special response before normal processing:

- Slack `url_verification` returns the provided challenge.
- Discord ping returns the ping response type.
- LINE usually accepts a normal HTTP 200 acknowledgement.

If processing continues asynchronously, return the provider ack first and let
the `ResponseAdapter` deliver the eventual reply.

## Generic Webhook Profile

A generic webhook should use the same external input path:

```json
{
  "provider": "webhook",
  "event_id": "build_123",
  "kind": "event",
  "text": "Build failed on main",
  "metadata": {
    "repository": "example/repo",
    "status": "failed"
  }
}
```

The profile decides whether this becomes a chat message, an agent task, a flow
trigger, or an ignored event.

## Public URLs

A webhook needs a reachable URL, but the URL provider is outside the framework.
Cloudflare Quick Tunnel may provide a temporary development URL, yet the
runtime should treat it as a swappable provider. The same webhook contract must
work behind localhost, a reverse proxy, a platform route, or any other tunnel.

