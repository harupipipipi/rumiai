# Interfaces

## Inputs

- `goal`: The requested user outcome.
- `context`: Local files, connector handoffs, screenshots, logs, or prior artifacts as applicable.
- `constraints`: Safety, budget, privacy, schedule, or runtime boundaries.
- `handoff_target`: The pack or tool surface that should execute or receive the result.

## Outputs

- `plan`: Domain-specific phased plan.
- `evidence`: References needed to prove completion.
- `handoff`: Explicit owner pack and next action.
- `status`: done, needs_review, blocked, or unsafe.

## Rich Assets

- `catalog/business_ops_workflows.yaml`: base workflow phases.
- `catalog/workflow_taxonomy.yaml`: detailed taxonomy for support, sales, marketing, procurement, CRM, and admin lanes.
- `policies/business_ops_safety.policy.yaml`: core local-first safety policy.
- `policies/approval_risk_matrix.policy.yaml`: approval and risk classification matrix.
- `ledgers/business_ops_handoff_ledger.schema.yaml`: required handoff evidence records.
- `checklists/operator_handoff.checklist.yaml`: operator review checklist before execution handoff.

## Required Secrets

None.
