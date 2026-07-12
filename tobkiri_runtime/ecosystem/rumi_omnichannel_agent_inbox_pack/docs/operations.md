# Operations

## Installation

Install `defaultspack` first, then select `rumi_omnichannel_agent_inbox_pack` as a separate setup pack.

## Review Gates

- Run the contract test for this pack.
- Confirm `asset_index.yaml` and `ecosystem.json` list every pack file.
- Confirm `supports_all_ok` is false.
- Confirm adjacent actions remain handoffs.
- Confirm remote input has no approval, execution, install, settings, or token authority.
- Confirm route idempotency and draft hash/expiry checks are represented in schemas and examples.
- Confirm no provider client code, secrets, or pre-auth routes are present.

## Failure Handling

If evidence, consent, approval, or ownership is missing, return a blocked packet or Handoff packet. Do not silently execute the next action.
