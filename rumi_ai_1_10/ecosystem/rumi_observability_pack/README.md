# Rumi Observability Pack

Rumi Observability Pack makes agent work inspectable: run ledgers, tool-call evidence, cost/latency summaries, failure taxonomy, and postmortems. It complements model evals, security, and devops packs without becoming a telemetry backend.

## Included Assets

- `schemas/observability_event.schema.json` defines event IDs, privacy classes, redaction state, cost units, latency units, and evidence references.
- `catalog/run_ledger_contract.yaml` defines required run-ledger fields and handoff rules.
- `policies/privacy_cost_redaction.policy.yaml` protects prompts, connector payloads, private URLs, account identifiers, and cost records.
- `checklists/incident_review_checklist.yaml` makes incident review evidence explicit before closure or handoff.
- `templates/postmortem_template.md` provides a local-first postmortem outline for redacted incident reports.

## Required Secrets

None.

## Network

None by default. The pack records and reviews local evidence; it does not export telemetry or fetch remote logs.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
