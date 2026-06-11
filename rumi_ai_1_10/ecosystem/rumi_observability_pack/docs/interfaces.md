# Interfaces

## Inputs

- `goal`: The requested user outcome.
- `context`: Local files, connector handoffs, screenshots, logs, or prior artifacts as applicable.
- `constraints`: Safety, budget, privacy, schedule, or runtime boundaries.
- `handoff_target`: The pack or tool surface that should execute or receive the result.
- `event`: A record matching `schemas/observability_event.schema.json` when event-level review is requested.
- `run_ledger`: A local ledger matching `catalog/run_ledger_contract.yaml` when run-level review is requested.

## Outputs

- `plan`: Domain-specific phased plan.
- `evidence`: References needed to prove completion.
- `handoff`: Explicit owner pack and next action.
- `status`: done, needs_review, blocked, or unsafe.
- `redaction_summary`: Privacy class, redaction state, and removed field categories.
- `cost_latency_summary`: Cost kind, currency or unit, latency unit, sample count, and pricing source.
- `incident_review`: Trigger, blast radius, cost/latency impact, owner handoff, and followups.

## Events

The pack recognizes `agent_run`, `tool_call`, `model_call`, `cost_latency`, `incident`, and `handoff` events. Each event needs an `event_id`, `run_id`, `owner_pack`, `privacy_class`, `redaction_state`, and non-empty `evidence_refs`.

## Ledgers

Run ledgers must include start and completion status, involved packs, model and tool call counts, cost summary, latency summary, evidence references, and redaction summary. Ledgers should be local review artifacts; they are not evidence that execution work was completed unless the owner pack evidence is attached.

## Required Secrets

None.

## Network

None by default. External log export, remote telemetry shipping, and connector payload publication are out of scope for this declarative pack.

## Grants

`defaultspack` owns grant selection and enforcement. This pack requests no executable grants and no host execution.
