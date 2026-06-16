# Operations

Use `rumi_knowledge_marketplace_pack` when the requested work fits its owner surfaces: skill_cards, template_catalogs, install_candidate_reviews, trust_metadata. Start by collecting enough evidence, then route any overlapping execution to the owner pack named in setup metadata. Do not treat a generated plan as completed work until the relevant evidence proves the requested outcome.

## Review Flow

1. Classify the candidate as skill, template, playbook, connector card, or pack bundle.
2. Validate card fields against `marketplace_card.schema.json` and the YAML card catalog.
3. Record provenance before any trust decision: source ref, content digest, publisher, reviewer, review time, permission summary, and blacklist status.
4. Apply the trust rubric and promotion/blacklist policy.
5. Keep auto-install disabled; require explicit user approval for install-ready status.
6. Route overlap to the owner pack: suspicious content to `rumi_security_review_pack`, connector execution to `rumi_connector_gateway_pack`, learned-skill memory to `rumi_memory_knowledge_pack`, and bundle composition to `rumi_pack_suite_pack`.

## Focused Verification

- Parse every JSON and YAML asset.
- Run `validate_ecosystem` against `ecosystem.json`.
- Confirm `metadata.asset_index` names every shipped pack asset.
- Confirm setup metadata remains marketplace-verified, signing-verified, `supports_all_ok: false`, and defaultspack promotion disabled.
- Reject generic placeholder examples and secret-like payloads.

## Common Failure Modes

- A card has no content digest or source reference.
- A connector card describes secrets without routing to connector gateway.
- A trusted card has no reviewer or review timestamp.
- A promotion decision ignores excessive permissions or suspicious network requirements.
- A blocked card lacks a blacklist reason or recheck path.
