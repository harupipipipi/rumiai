# Authority Test Harness

Authority QA runs must not disable production approval semantics. The test
harness is an opt-in helper for local, CI, or development profiles that settles
real Authority requests through the normal service approval and denial methods.

## Enablement

Set these values for HTTP-driven QA:

- `RUMI_AUTHORITY_TEST_MODE=1`
- `RUMI_AUTHORITY_TEST_TOKEN=<random test token>`
- `RUMI_PANEL_BOOTSTRAP_SECRET=<test signing secret>`

The mode is rejected when production or packaged markers such as
`RUMI_ENVIRONMENT=production`, `RUMI_BUILD_CHANNEL=production`, or
`RUMI_PACKAGED=1` are present unless the active runtime profile is explicitly
`dev`, `development`, `test`, `testing`, `ci`, or `local`.

## Policy Rules

Every settlement needs a scoped rule. A rule must name `permission_id` and
match at least one resource field.

```json
{
  "version": 1,
  "rules": [
    {
      "rule_id": "qa-model-openai",
      "decision": "approve",
      "permission_id": "model.invoke",
      "resource": {"provider_id": "openai"},
      "scope": "once",
      "expires_in_seconds": 60
    }
  ]
}
```

Supported decisions are `approve`, `deny`, `synthetic_timeout`,
`synthetic_cancel`, and `require_synthetic`.

## HTTP Helper

Post to `/api/authority/test/settle` with the test token in
`X-Rumi-Authority-Test-Token` or `authority_test_token`.

The approve response includes `authority_followup` and `authority_followups`
objects that contain the real one-shot approval token for the original request.
Feed those back through the normal chat/run metadata path; do not send
client-supplied `approved` flags.

The harness records `authority_test_harness_*` audit events with
`authority_mode: test`, rule id, scenario id, permission id, and resource hash.
Tokens remain one-shot, deny/cancel does not create grants, timeout marks only a
pending request as expired, and duplicate/racing settlement still fails closed.

Never enable this mode for packaged production builds or use it as a general
auto-approve path.
