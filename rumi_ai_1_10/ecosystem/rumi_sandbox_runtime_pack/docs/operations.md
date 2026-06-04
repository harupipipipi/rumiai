# Operations

Use `rumi_sandbox_runtime_pack` when the requested work fits its owner surfaces: sandbox_contracts, runtime_isolation_matrix, execution_evidence, artifact_job_boundaries. Start by collecting enough evidence, then route any overlapping execution to the owner pack named in setup metadata. Do not treat a generated plan as completed work until the relevant evidence proves the requested outcome.

## Review Checklist

- Classify the execution boundary before recommending a runtime.
- Reject raw secret values and ambient host environment inheritance.
- Require explicit approval for host mutation, network access, remote execution, and release jobs.
- Require a runtime receipt and reproducibility checklist for every accepted execution result.
- Hand off desktop/browser actions to computer-control owners and release/deploy jobs to devops-release owners.
