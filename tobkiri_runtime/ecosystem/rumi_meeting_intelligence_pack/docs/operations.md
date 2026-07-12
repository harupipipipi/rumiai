# Operations

## Install

Select `rumi_meeting_intelligence_pack` as a setup pack. It depends on `defaultspack >=2.0.0`.

## Test

Run `python -m pytest -q tobkiri_runtime/tests/test_rumi_meeting_intelligence_pack_contract.py`.

## Failure Modes

Missing evidence, owner ambiguity, unsafe requests, absent participant consent, or attempts to execute adjacent-domain actions must block the quality gate and produce a handoff.

## Rollback And Revocation

Remove the setup pack selection. No credentials, background jobs, or runtime grants are created by this pack.

## Manual Review Points

Review evidence links, transcript source spans, assumptions, protected records, owner handoffs, draft-only follow-ups, and defaultspack promotion blockers before treating output as production-ready.
