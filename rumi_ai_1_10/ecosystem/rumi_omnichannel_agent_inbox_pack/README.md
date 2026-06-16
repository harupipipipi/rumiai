# Rumi Omnichannel Agent Inbox Pack

Declarative omnichannel agent inbox contracts for channel payloads, identity mapping, ACL gates, thread routing, outbound draft approvals, notification preferences, and inbox UI review.

This setup pack makes Rumi more customizable by adding a domain contract that can be selected independently from defaultspack. It is intentionally local-first, declarative, and reviewable: it creates schemas, workflow packets, quality gates, and handoff records instead of executing adjacent runtime actions.

## Provides

- channel_payload_contract
- identity_mapping
- channel_acl
- thread_to_agent_routing
- outbound_draft_approval
- notification_preferences
- inbox_thread_state
- inbox_ui_contract

## Does Not Provide

- actual app connectors
- Slack client
- Gmail client
- mobile client
- work execution
- schedule execution
- security policy review
- message sending

## Required Secrets

None. Network is denied by default and the pack contains no executable runtime code, provider client, OAuth secret, bot token, refresh token, or pre-auth route.

## Safety Contract

- Channel ACLs deny by default and remote input cannot elevate them.
- Thread routes are idempotent: the same key returns the same decision instead of creating duplicate work.
- Outbound approvals bind one draft body hash to an expiry and a single-use receipt.
- Remote input cannot approve tools or drafts, execute work, install packs, mutate settings, or issue approval tokens.

## Defaultspack Promotion

Not eligible by default. Promotion requires:

- requires_channel_identity_registry
- requires_external_message_approval_tokens
- connector_io_owned_elsewhere
- security_acl_review_required
- must_prove_outbound_draft_gate
- must_prove_remote_input_has_no_authority
- must_prove_route_idempotency

## Overlap Rule

If another pack can perform a step, Rumi should prefer the narrower owner surface. This pack emits a Handoff packet whenever the request crosses into runtime execution, connector IO, persistence, scheduling, security review, or media transformation.
