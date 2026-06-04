# Interfaces

## Inputs

- Local user-supplied artifacts or records emitted by adjacent owner packs.
- Schema IDs listed in `ecosystem.json`.
- Evidence IDs, review state, idempotency keys, body hashes, and handoff owner labels.

Remote input is allowed to submit normalized payload evidence only. It cannot approve drafts or tools, execute work, install packs, mutate settings, elevate ACLs, or issue approval tokens.

## Outputs

- Draft packets.
- Review checklist packets.
- Handoff packets for owner packs.
- UI contract templates for host surfaces to render.

Outbound draft approvals must include a `sha256` body hash, expiry, local approver reference, and single-use receipt semantics before a connector-owner handoff can send anything.

## Optional Integrations

- `rumi_connector_gateway_pack`: Owns connector authentication and external channel IO.
- `rumi_agent_services_pack`: Executes routed work after inbox approval.
- `rumi_workflow_scheduler_pack`: Schedules notification windows and follow-ups.
- `rumi_security_review_pack`: Reviews channel ACL and risky outbound policies.
- `rumi_business_ops_pack`: Owns business workflow actions after inbox routing.
- `rumi_voice_mobile_pack`: Owns mobile voice and notification surfaces.

## Required Secrets

None.

## Does Not Provide

- actual app connectors
- Slack client
- Gmail client
- mobile client
- work execution
- schedule execution
- security policy review
- message sending
