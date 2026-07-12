# Operations

## Install

Select `rumi_prompt_studio_pack` as a setup pack. It depends on `defaultspack >=2.0.0`.

## Test

Run `python -m pytest -q tobkiri_runtime/tests/test_rumi_prompt_studio_pack_contract.py`.

## Failure Modes

Missing evidence, owner ambiguity, unsafe requests, or attempts to execute adjacent-domain actions must block the quality gate and produce a handoff.

## Rollback And Revocation

Remove the setup pack selection. No credentials, background jobs, or runtime grants are created by this pack.

## Manual Review Points

Review evidence links, assumptions, protected records, owner handoffs, and defaultspack promotion blockers before treating output as production-ready.

## Version Ledger

Every prompt artifact release must update `ledgers/prompt_version_ledger.yaml` with prompt id, version, fixture ids, change summary, status, and non-overlap compatibility notes.
