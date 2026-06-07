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

- `external_connector_gateway_owner`: Owns connector authentication and external channel IO.
- `external_agent_services_owner`: Executes routed work after inbox approval.
- `external_workflow_scheduler_owner`: Schedules notification windows and follow-ups.
- `external_security_review_owner`: Reviews channel ACL and risky outbound policies.
- `external_business_ops_owner`: Owns business workflow actions after inbox routing.
- `external_voice_mobile_owner`: Owns mobile voice and notification surfaces.

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
