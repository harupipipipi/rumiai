# Interfaces

## Inputs

- `goal`: The requested user outcome.
- `context`: Local files, connector handoffs, screenshots, logs, or prior artifacts as applicable.
- `constraints`: Safety, budget, privacy, schedule, or runtime boundaries.
- `handoff_target`: The pack or tool surface that should execute or receive the result.
- `marketplace_card`: A card matching `schemas/marketplace_card.schema.json`.
- `requirement_set`: Tag requirements matching `schemas/marketplace_requirement.schema.json`.
- `provider_inventory`: Installed and reviewed packs, skills, tools, MCP descriptors, model capability records, and extensions with provided tags.
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
- `requirement_resolution`: Satisfied, optional-missing, search-needed, approval-needed, or blocked results for each tag requirement.
- `marketplace_search_intent`: A non-executing search request containing kind, tags, match mode, version, model tier, and reason.

## Card Contract

Cards describe capability metadata only. They must disclose `card_id`, `capability_type`, `source`, `publisher`, `trust_status`, `permission_summary`, `provenance`, and `install_review`. Cards may additionally publish free-form `tags`, `provides`, tag-based `requirements`, a provider-independent `model_policy`, extension points, and listing status.

`card_id` is a stable provenance and ledger key. It is not a dependency selector. A connector or MCP card can describe runtime requirements, but live execution, secrets, and grants remain with the relevant gateway and `defaultspack`.

## Tag Requirement Contract

- Tags are human-readable and free-form; UUID-shaped selectors are rejected by the schema.
- Top-level requirement entries are combined with AND.
- Within an entry, `selector.match: any` accepts one listed tag; `all` requires every listed tag.
- `kind` is extensible. Well-known kinds are `pack`, `skill`, `tool`, `mcp_tool`, `mcp_server`, `model`, and `extension`.
- `prefer_pack` defaults to true so reviewed packs are resolved before loose assets.
- `marketplace_fallback` may propose search or an install-review handoff, but never grants or installs automatically.

## Model Tier Contract

`catalog/model_tiers.yaml` maps `rough`, `standard`, `strong`, and `frontier` to defaultspack model capabilities and groups. Cards may combine a tier with model tags such as `tool_calling`, `vision`, `structured_output`, or `coding`. Concrete model selection stays with defaultspack.

## Required Evidence

Every install-ready decision needs a content digest, reviewer, review timestamp, trust rubric level, permission summary, blacklist status, requirement-resolution evidence, and explicit user approval. Missing provenance or unresolved required tags keeps the status at `needs_review`.

## Marketplace Preview

The discovery interface is intentionally non-executing. Until a reviewed remote registry and install handoff exist, the UI exposes `Marketplace`, `Coming soon`, and a disabled `探す` action.

## Required Secrets

None.

## Network

None by default. This pack cannot use network access to fill missing card metadata or satisfy tag requirements. External discovery and connector runtime behavior belong to other packs.

## Grants

`defaultspack` owns grant selection and enforcement. This pack requests no executable grants and no host execution.
