# Rumi Business Ops Pack

Rumi Business Ops Pack organizes AI-agent service work for sales follow-ups, support triage, marketing briefs, procurement comparisons, CRM hygiene, and admin operations. It mirrors the practical reach of Genspark/Manus/OpenClaw style agents while keeping connector execution, scheduling, and workspace artifacts in their owning packs.

## Quality Assets

- `catalog/workflow_taxonomy.yaml` classifies business operations by owner surface, evidence, risk, and handoff owner.
- `policies/approval_risk_matrix.policy.yaml` defines approval gates for external messages, CRM changes, procurement recommendations, scheduling, and money/contract risk.
- `ledgers/business_ops_handoff_ledger.schema.yaml` and `checklists/operator_handoff.checklist.yaml` make handoffs auditable before connector, scheduler, workspace, or research packs execute anything.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
