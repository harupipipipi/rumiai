# Operations

## Install

Select `rumi_localization_pack` as a setup pack. It depends on `defaultspack >=2.0.0`.

## Test

Run `python -m pytest -q rumi_ai_1_10/tests/test_rumi_localization_pack_contract.py`.

## Failure Modes

Missing segment evidence, glossary ambiguity, protected-term exceptions, owner ambiguity, unsafe requests, or attempts to execute adjacent-domain actions must block the quality gate and produce a handoff.

## Rollback And Revocation

Remove the setup pack selection. No credentials, background jobs, or runtime grants are created by this pack.

## Manual Review Points

Review evidence links, assumptions, locale issue records, protected-term decisions, owner handoffs, and defaultspack promotion blockers before treating output as production-ready.

## Triage Flow

1. Confirm source and target segment IDs exist.
2. Check glossary and protected-term policy.
3. Classify issues with `schemas/locale_issue.schema.json`.
4. Complete `checklists/localization_review.checklist.yaml`.
5. Produce a handoff packet when the next action belongs to document, frontend, workspace, connector, QA, or eval owners.
