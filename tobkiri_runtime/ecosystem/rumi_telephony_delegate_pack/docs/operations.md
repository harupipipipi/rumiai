# Operations

## Enablement

Install `defaultspack` first, then enable `rumi_telephony_delegate_pack` as a separate setup pack. Do not place it into defaultspack until promotion evidence is accepted.

## Review

Run the contract test for this pack, inspect the quality matrix, and confirm all overlap policy entries are still correct. Approval evidence must show the human approver, number alias, script ID, consent disclosure review, and never-call screening result.

## Approval And Abort Rules

- Do not produce provider handoff unless approval state is approved and the approval receipt is evidence-linked.
- Do not continue after declined consent; return an aborted session packet with takeover required.
- Do not continue when the intent is outside the allowed intent enum; return a blocked packet.
- Do not forward transcript content until configured PII classes have replacement segments and review state is not blocked.
- Do not resolve takeover internally; name the human or owner pack responsible for the next step.

## Failure Handling

If evidence is missing, return a blocked packet or uncertainty note. If the request needs external state mutation, produce a Handoff packet for the owner pack. If ownership overlaps with another pack, prefer the more specific owner surface and keep this pack in draft-only mode.

## Required Secrets

None.
