# Operations

## Install

Select `rumi_sop_mining_pack` as a setup pack. It depends on `defaultspack >=2.0.0`.

## Test

Run `python -m pytest -q rumi_ai_1_10/tests/test_rumi_sop_mining_pack_contract.py`.

## Failure Modes

Missing evidence, owner ambiguity, unsafe requests, or attempts to execute adjacent-domain actions must block the quality gate and produce a handoff.

## Rollback And Revocation

Remove the setup pack selection. No credentials, background jobs, or runtime grants are created by this pack.

## Manual Review Points

Review evidence links, assumptions, protected records, redaction classes, source consent basis, owner handoffs, human approver role, approval record reference, and defaultspack promotion blockers before treating output as production-ready. Automation, browser, computer, scheduler, tool, and observability actions stay outside this pack.
