# Operations

## Enablement

Install `defaultspack` first, then enable `rumi_experiment_design_pack` as a separate setup pack. Do not place it into defaultspack until promotion evidence is accepted.

## Review

Run the contract test for this pack, inspect the quality matrix, and confirm all overlap policy entries are still correct.

For decision records, confirm `available_data_state` and `result_claim.status` agree. Design-only and insufficient-data packets must not claim a winner, significance, lift, or metric movement. Requests to run SQL, analytics queries, or statistical calculations must produce a data-analysis handoff.

## Failure Handling

If evidence is missing, return a blocked packet or uncertainty note. If the request needs external state mutation, produce a Handoff packet for the owner pack. If ownership overlaps with another pack, prefer the more specific owner surface and keep this pack in draft-only mode.

## Required Secrets

None.
