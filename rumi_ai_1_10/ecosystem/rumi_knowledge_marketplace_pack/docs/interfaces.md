# Interfaces

## Inputs

- `goal`: The requested user outcome.
- `context`: Local files, connector handoffs, screenshots, logs, or prior artifacts as applicable.
- `constraints`: Safety, budget, privacy, schedule, or runtime boundaries.
- `handoff_target`: The pack or tool surface that should execute or receive the result.
- `marketplace_card`: A card matching `schemas/marketplace_card.schema.json`.
- `install_candidate`: A local candidate with source reference, publisher, permission summary, trust status, and install-review context.
- `provenance_record`: A ledger entry matching `ledgers/provenance_ledger.yaml`.

## Outputs

- `plan`: Domain-specific phased plan.
- `evidence`: References needed to prove completion.
- `handoff`: Explicit owner pack and next action.
- `status`: done, needs_review, blocked, or unsafe.
- `trust_decision`: unreviewed, repository_reviewed, trusted, or blocked.
- `permission_summary`: Required permissions, network requirement, secret requirement, and host execution requirement.
- `install_review`: allow_install, allow_with_warning, needs_security_review, or block_install.
- `provenance_ledger_entry`: Source ref, content digest, publisher, reviewer, trust status, permission summary, and blacklist status.

## Card Contract

Cards describe capability metadata only. They must disclose `card_id`, `capability_type`, `source`, `publisher`, `trust_status`, `permission_summary`, `provenance`, and `install_review`. A connector card can describe connector requirements, but live connector execution and secrets remain with `rumi_connector_gateway_pack`.

## Required Evidence

Every install-ready decision needs a content digest, reviewer, review timestamp, trust rubric level, permission summary, blacklist status, and explicit user approval. Missing provenance keeps the status at `needs_review`.

## Required Secrets

None.

## Network

None by default. This pack cannot use network access to fill missing card metadata. External discovery and connector runtime behavior belong to other packs.

## Grants

`defaultspack` owns grant selection and enforcement. This pack requests no executable grants and no host execution.
