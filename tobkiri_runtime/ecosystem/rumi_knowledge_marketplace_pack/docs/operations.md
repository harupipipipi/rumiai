# Operations

Use `rumi_knowledge_marketplace_pack` when the requested work fits its owner surfaces: skill cards, tool and MCP cards, template catalogs, tag requirements, install candidate reviews, trust metadata, and Marketplace preview metadata. Start by collecting enough evidence, then route overlapping execution to the owner pack named in setup metadata. Do not treat a generated plan or tag match as completed work until the relevant evidence proves the requested outcome.

## Review Flow

1. Classify the candidate as skill, tool, MCP tool or server, template, playbook, extension, connector card, or pack bundle.
2. Validate card fields against `marketplace_card.schema.json`, `marketplace_requirement.schema.json`, and the YAML catalogs.
3. Normalize and review free-form tags. Keep broad and specific tags when both aid discovery; reject UUID-shaped requirement selectors.
4. Evaluate top-level requirements with AND. Evaluate each selector using its declared `any` or `all` mode and excluded tags.
5. Resolve approved installed packs first when `prefer_pack` is true. Then consider pack-supplied assets, reviewed standalone assets, and finally a non-executing Marketplace search handoff.
6. Map model tier and required model tags to defaultspack capabilities without pinning the card to a provider-specific model ID.
7. Record provenance before any trust decision: source ref, content digest, publisher, reviewer, review time, permission summary, requirement evidence, and blacklist status.
8. Apply the trust rubric and promotion/blacklist policy.
9. Keep auto-install disabled; require explicit user approval for install-ready status.
10. Route overlap to the owner pack: suspicious content to `rumi_security_review_pack`, MCP review to `rumi_mcp_gateway_pack`, connector execution to `rumi_connector_gateway_pack`, model routing to `defaultspack`, learned-skill memory to `rumi_memory_knowledge_pack`, and bundle composition to `rumi_pack_suite_pack`.

## Requirement Resolution Status

- `satisfied`: an approved provider satisfies the selector and any version or model-tier constraint.
- `optional_missing`: no provider matched, but the requirement is optional.
- `search_needed`: no provider matched and Marketplace search may be offered.
- `approval_needed`: a candidate matched but still needs normal install, connector, or MCP approval.
- `blocked`: a required selector matched only blocked candidates or violates an exclusion.

A search result is evidence for discovery only. It is not evidence that the dependency is installed, approved, connected, or runnable.

## Marketplace Preview

Until registry search and install handoff are implemented, expose the Marketplace card as `Coming soon` and keep the `探す` button disabled. Do not silently replace that action with network access.

## Focused Verification

- Parse every JSON and YAML asset.
- Run `validate_ecosystem` against `ecosystem.json`.
- Confirm `metadata.asset_index` names every shipped pack asset.
- Confirm tag selectors support `any` and `all`, reject UUID-shaped values, and default to pack-first resolution.
- Confirm model tiers include `rough`, `standard`, `strong`, and `frontier`, with high-impact exclusions for rough use.
- Confirm setup metadata remains marketplace-verified, signing-verified, `supports_all_ok: false`, and defaultspack promotion disabled.
- Reject generic placeholder examples and secret-like payloads.

## Common Failure Modes

- A card has no content digest or source reference.
- A requirement uses a card ID or UUID instead of compatibility tags.
- An `all` selector is accidentally evaluated as `any`, or separate top-level requirements are accidentally ORed.
- A loose tool is selected even though an approved pack satisfies the same requirement and `prefer_pack` is true.
- A rough-tier model silently performs a security, trust, destructive, or high-impact final decision.
- A connector or MCP card describes secrets without routing to the correct gateway.
- A trusted card has no reviewer or review timestamp.
- A promotion decision ignores excessive permissions or suspicious network requirements.
- A blocked card lacks a blacklist reason or recheck path.
