# Interfaces

## Inputs

Accepted inputs are references to already available evidence:

- local chat transcript excerpts
- tool call and tool result traces
- audit log records
- test command summaries
- human handoff notes
- approval or rejection notes

Each input must include a trace identifier, source type, timestamp or ordering key, evidence reference, consent basis, scope boundary, and redaction status.

## Outputs

The pack documents, but does not execute:

- SOP records that follow `schemas/sop_record.schema.json`
- runbook drafts based on `runbooks/sop_mining_runbook.template.yaml`
- review checklists based on `checklists/sop_mining_review.checklist.yaml`
- ledger entries based on `ledgers/sop_mining_ledger.schema.yaml`
- human-approved workflow recipe records from `catalog/workflow_recipe_catalog.yaml`

## Required Secrets

None.

## Network

None by default. This pack does not open network connections and does not fetch missing evidence.

## Grants

No grants are required. The pack provides no executable tool, route, handler, scheduled job, or background worker.

## Handoff

When a request requires live capture, automation execution, browser control, computer control, scheduling, tool creation, or message delivery, the reviewer must stop SOP mining and hand off to the owner pack listed in setup metadata. The SOP Mining Pack may record the handoff reason after the owner pack has produced evidence.
