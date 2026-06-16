# Interfaces

## Inputs

- `goal`: The requested user outcome.
- `context`: Local files, connector handoffs, screenshots, logs, or prior artifacts as applicable.
- `constraints`: Safety, budget, privacy, schedule, or runtime boundaries.
- `handoff_target`: The pack or tool surface that should execute or receive the result.
- `boundary_classification`: local_read_only, local_host_mutating, container_ephemeral, remote_ssh, or browser_or_desktop.
- `secret_mount_request`: none, named runtime secret reference, raw secret value, or inherited host environment.

## Outputs

- `plan`: Domain-specific phased plan.
- `evidence`: References needed to prove completion.
- `handoff`: Explicit owner pack and next action.
- `status`: done, needs_review, blocked, or unsafe.
- `runtime_receipt`: Receipt schema reference and evidence summary after approved execution.
- `reproducibility_checklist`: Required evidence for future reruns.

## Schemas And Policies

- Execution boundaries: `specs/execution_boundary_matrix.yaml`
- Secret mounts: `policies/secret_mount.policy.yaml`
- Runtime receipts: `specs/runtime_receipt.schema.yaml`
- Reproducibility: `checklists/reproducibility_checklist.yaml`
- Receipt ledger: `evidence/runtime_receipt_ledger.template.yaml`

## Required Secrets

None.
