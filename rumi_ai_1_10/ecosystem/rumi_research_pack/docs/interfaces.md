# Interfaces

## Flows

This pack declares no flows.

## Functions and Handlers

This pack declares no executable functions or handlers. Entries in `catalog/capabilities.research.json` are interface contracts only.

## Routes

This pack declares no HTTP routes or local API routes.

## Events

The pack names lifecycle states for implementations to use, but does not publish or subscribe to events. Suggested states include `planned`, `collected`, `triaged`, `cited`, `synthesized`, `reviewed`, and `handed_off`.

## Stores

No store is required by this pack. Implementations that materialize evidence should store evidence cards, source manifests, and citation maps in runtime-approved workspace storage.

## Required Secrets

`required_secrets` is empty. The pack must not contain provider keys, bearer tokens, private crawler credentials, connector tokens, or personal account credentials.

## Network

Network access is `none_by_default`. Local files, user-provided notes, pasted sources, and already-available workspace artifacts are the default inputs. Runtime implementations may request network grants for search or retrieval, but that grant belongs to the implementation pack, not this pack.

## Grants

The catalog uses declarative grant names for risk reasoning:

- `research.read_local_sources`
- `research.write_evidence`
- `research.review_sources`
- `research.write_synthesis`
- `artifact.preview`

Optional implementation grants may include `network.read` or connector-specific grants, but they are not requested by this pack.

## Catalog Files

- `catalog/capabilities.research.json`: named research capabilities with expected inputs, outputs, grants, and risk levels.
- `catalog/evidence_schema.research.yaml`: evidence card, source manifest, and citation map fields.
- `catalog/source_quality.research.yaml`: source quality dimensions and review labels.
- `catalog/workflows.research.yaml`: local-first research workflow recipes.
- `catalog/citation_styles.research.yaml`: citation style options and traceability rules.

## Profiles, Presets, and Prompts

- `profiles/deep_researcher.profile.yaml`: full research planning, evidence, and synthesis profile.
- `profiles/evidence_reviewer.profile.yaml`: source review and contradiction-focused profile.
- `profiles/local_research_synthesizer.profile.yaml`: local-only synthesis profile.
- `presets/*.preset.yaml`: task modes inspired by deep research reports and citation workflows.
- `prompts/*.system.md`: reusable system prompts for implementation packs to load.
