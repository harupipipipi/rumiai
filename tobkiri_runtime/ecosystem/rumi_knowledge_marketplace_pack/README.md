# Rumi Knowledge Marketplace Pack

Rumi Knowledge Marketplace Pack defines how Rumi catalogues reusable skills, tools, MCP surfaces, templates, playbooks, extensions, connector cards, and pack bundles. It borrows from OpenClaw skills and Hermes skills, but treats marketplace content as untrusted until reviewed.

The pack is declarative. It prepares searchable metadata, trust evidence, provenance, install review, and dependency handoff contracts; `defaultspack` remains the owner of runtime grants, active pack selection, model routing, and MCP execution.

## Included Assets

- `schemas/marketplace_card.schema.json` defines cards, free-form tags, provided capabilities, tag requirements, model policy, extension points, listing status, permissions, provenance, trust status, and install review.
- `schemas/marketplace_requirement.schema.json` defines `any` and `all` tag selectors for packs, skills, tools, MCP tools, models, and extensible requirement kinds.
- `catalog/model_tiers.yaml` defines provider-independent `rough`, `standard`, `strong`, and `frontier` usage tiers, including the low-risk `雑に使ってよい` tier.
- `catalog/trust_rubric.yaml` defines unreviewed, repository-reviewed, trusted, and blocked states.
- `workflows/install_review_workflow.yaml` defines local-first review phases and explicit approval requirements.
- `ledgers/provenance_ledger.yaml` defines the digest, reviewer, status, permission, and blacklist evidence needed for each candidate.
- `policies/promotion_blacklist.policy.yaml` defines promotion requirements, blockers, blacklist reasons, and recheck rules.
- `docs/tag-requirements.md` defines normalization, pack-first resolution, marketplace fallback, and extensibility rules.

## Tag and Pack Contract

Requirements are selected with human-readable tags rather than UUIDs. Tags are free-form, so broad tags such as `coding` can coexist with more specific tags such as `coding.python.refactor`. A selector may require `any` listed tag or `all` listed tags.

`prefer_pack` defaults to true. Matching, approved packs are considered before loose skill, tool, MCP, or extension candidates. Discovery never grants access or installs content automatically; it produces a reviewed handoff to the existing approval path.

## Marketplace Preview

The Tools workspace exposes a stable preview route labelled `Marketplace`, `Coming soon`, and `探す`. Pressing `探す` opens the preview panel only; remote discovery, result review, and install handoff are not implemented yet.

## Required Secrets

None.

## Network

None by default. Marketplace cards may describe connector or remote capabilities, but this pack does not fetch candidates, install content, connect MCP servers, or grant connector access.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, runtime enforcement, and model routing. Related packs own their execution surfaces. This pack contributes schemas, policies, profiles, prompts, presets, examples, evidence, and handoff contracts for its own surface.
