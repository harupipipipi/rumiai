# Rumi Observability Pack Docs

These docs describe the declarative contract for `rumi_observability_pack`. The pack does not add executable runtime behavior; it provides pack-specific structure for planning, review, and handoff.

Read the docs in this order:

1. `architecture.md` for ownership boundaries and local-first asset flow.
2. `interfaces.md` for input/output fields, events, ledgers, secrets, network, and grants.
3. `operations.md` for checklist-driven review, redaction, and focused verification.

Primary assets:

- Event schema: `schemas/observability_event.schema.json`
- Run ledger contract: `catalog/run_ledger_contract.yaml`
- Privacy and cost redaction: `policies/privacy_cost_redaction.policy.yaml`
- Incident review: `checklists/incident_review_checklist.yaml`
- Postmortem template: `templates/postmortem_template.md`
