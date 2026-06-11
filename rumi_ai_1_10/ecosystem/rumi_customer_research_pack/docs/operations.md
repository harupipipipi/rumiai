# Operations

## Enablement

Install `defaultspack` first, then enable `rumi_customer_research_pack` as a separate setup pack. Do not place it into defaultspack until promotion evidence is accepted.

## Review

Run the contract test for this pack, inspect the quality matrix, and confirm all overlap policy entries are still correct. Manual review must verify that revoked or do_not_use participants are excluded, source_quote_ids resolve to redacted allowed quotes, and insight cards do not contain raw personal identifiers.

## Failure Handling

If evidence is missing, return a blocked packet or uncertainty note. If consent is revoked or allowed_use is do_not_use, return a blocked packet and do not create an insight card. If the request needs external state mutation or generic web research, produce a Handoff packet for the owner pack. If ownership overlaps with another pack, prefer the more specific owner surface and keep this pack in draft-only mode.

## Required Secrets

None.
