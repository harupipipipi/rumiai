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

- `catalog/frontend_workflows.yaml`: frontend workflow phases.
- `catalog/design_system_fit_rubric.yaml`: design-system fit scoring criteria.
- `catalog/responsive_qa_matrix.yaml`: viewport, screenshot, and defect-classification matrix.
- `schemas/component_acceptance.schema.yaml`: required acceptance fields for component briefs.
- `checklists/component_acceptance.checklist.yaml`: reviewer checklist for component readiness.

## Required Secrets

None.
