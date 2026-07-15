# Operations

Use `rumi_business_ops_pack` when the requested work fits its owner surfaces: sales_support_workflows, marketing_briefs, procurement_decision_memos, crm_hygiene_contracts. Start by collecting enough evidence, then route any overlapping execution to the owner pack named in setup metadata. Do not treat a generated plan as completed work until the relevant evidence proves the requested outcome.

## Review Steps

1. Classify the request using `catalog/workflow_taxonomy.yaml`.
2. Apply `policies/approval_risk_matrix.policy.yaml` before drafting external actions.
3. Complete `checklists/operator_handoff.checklist.yaml` before any connector, scheduler, workspace, or research handoff.
4. Record evidence in `ledgers/business_ops_handoff_ledger.schema.yaml`.
5. Treat money, contracts, legal, HR, and customer-facing sends as approval-gated.
