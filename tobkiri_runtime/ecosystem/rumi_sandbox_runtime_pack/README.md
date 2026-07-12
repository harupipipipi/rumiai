# Rumi Sandbox Runtime Pack

Rumi Sandbox Runtime Pack defines contracts for local, container, SSH, remote, and ephemeral execution environments. It draws on Hermes terminal backends and agent sandbox patterns, but remains declarative: actual execution stays with approved tools and defaultspack grants.

## Review Assets

- `specs/execution_boundary_matrix.yaml`: classifies local, container, remote, browser, and host-mutating execution boundaries.
- `policies/secret_mount.policy.yaml`: blocks raw secrets and ambient environment inheritance by default.
- `specs/runtime_receipt.schema.yaml`: defines receipt evidence expected from approved execution owners.
- `checklists/reproducibility_checklist.yaml`: records what makes a sandbox job reproducible.
- `evidence/runtime_receipt_ledger.template.yaml`: ledger template for accepted, caveated, blocked, and rejected runtime receipts.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
