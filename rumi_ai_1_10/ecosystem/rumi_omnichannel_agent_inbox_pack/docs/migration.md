# Migration

Existing company inbox behavior should migrate by emitting provider-neutral channel payloads and route decisions into this pack. Product-specific roles stay in operations company packs. Remote input can never approve tools, install packs, mutate settings, or issue approval tokens.

## Current Defaultspack Shape

Existing `CompanySlackRuntime`-style behavior should be treated as a compatibility source, not the reusable abstraction. Migration should normalize provider-specific records into `channel_payload`, link identities through `identity_map`, apply a default-deny `channel_acl`, then emit an idempotent `thread_route` decision.

## Required Compatibility Rules

- Same `thread_id + identity_id + acl_id + idempotency_key` returns the existing route decision.
- Outbound replies remain `outbound_draft` records until a local reviewer creates a non-expired `draft_approval` for the exact body hash.
- Connector owners receive handoff packets only; this pack does not fetch provider data or send messages.
- Remote input cannot approve outbound drafts, approve tools, execute work, install packs, mutate settings, issue approval tokens, or issue security tokens.
- Provider clients, provider SDK wiring, OAuth secrets, bot tokens, refresh tokens, mobile push clients, and pre-auth routes stay outside this pack.
