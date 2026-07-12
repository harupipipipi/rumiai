# Operations

## Enablement

Install `defaultspack` first, then enable `rumi_study_coach_pack` as a separate
setup pack. Do not place it into defaultspack until promotion evidence is
accepted. The pack should be activated only for sessions that can provide local
note IDs, learner goals, and reviewable source spans.

## Review

Run the contract test for this pack, inspect the quality matrix, and confirm all
overlap policy entries are still correct. A release reviewer should sample at
least one positive local-note quiz case and one insufficient-note case:

- the positive case must cite local notes on every quiz item
- the insufficient-note case must mark uncertainty and avoid fabricated facts
- scheduler, memory, research, document parsing, and workspace requests must be
  handoffs to owner packs
- `required_secrets`, `required_network`, and host execution must remain empty
  or false
- defaultspack promotion must remain false until blockers and evidence are
  explicitly cleared

## Failure Handling

If evidence is missing, return a blocked packet or uncertainty note. If the
request needs external state mutation, produce a Handoff packet for the owner
pack. If ownership overlaps with another pack, prefer the more specific owner
surface and keep this pack in draft-only mode.

## Evidence Ledger Audit

For each generated artifact, verify that every record has `source_ids`,
`source_spans`, `claim_summary`, `uncertainty`, `review_state`, and
`handoff_owner`. Do not accept a progress report that claims mastery from
uncited notes. Do not accept a review queue that silently writes reminders.

## Required Secrets

None.
