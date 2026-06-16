# Interfaces

## Flows

This pack declares no flows.

## Functions and Handlers

This pack declares no executable functions or handlers. Entries in `catalog/capabilities.memory.json` are interface contracts only.

## Routes

This pack declares no HTTP routes or local API routes.

## Events

The pack names memory lifecycle states for implementations to use, but does not publish or subscribe to events. Suggested states include `proposed`, `accepted`, `linked`, `superseded`, `stale`, `archived`, `rejected`, and `forgotten`.

## Stores

No store is required by this pack. Implementations may map specs to SQLite, files, vector indexes, document stores, or runtime memory managers, but those are outside this pack.

## Required Secrets

`required_secrets` is empty. The pack must not include provider keys, personal tokens, gateway credentials, connector tokens, or private endpoints.

## Network

Network access is `none_by_default`. Local session transcripts, user-provided notes, project files, and locally available evidence are the default inputs. Implementations that sync or retrieve remote memory must request their own grants outside this pack.

## Grants

Declarative grant names for downstream implementations:

- `memory.read_session`
- `memory.search_session`
- `memory.propose_update`
- `memory.review_update`
- `memory.archive`
- `knowledge.read_project`
- `knowledge.propose_update`
- `skill.propose`

This pack does not request grants at install time.

## Catalog and Spec Files

- `catalog/capabilities.memory.json`: named memory and knowledge capability contracts.
- `catalog/recall_workflows.memory.yaml`: local-first recall and curation workflow recipes.
- `catalog/surfaces.memory.json`: UI/runtime surface names and ownership notes.
- `specs/memory_objects.schema.yaml`: memory object, project knowledge, user profile, and evidence fields.
- `specs/skill_learning_proposal.schema.yaml`: proposal fields for creating or improving skills.
- `policies/memory_hygiene.policy.yaml`: retention, deduplication, contradiction, and sensitivity rules.
- `policies/recall_evidence.policy.yaml`: evidence-backed recall and confidence rules.
- `policies/skill_learning.policy.yaml`: rules for proposing, reviewing, and rejecting agent-learned skills.

## Profiles, Presets, and Prompts

- `profiles/memory_curator.profile.yaml`: memory hygiene and update proposal profile.
- `profiles/evidence_recall_reviewer.profile.yaml`: source-backed recall review profile.
- `profiles/project_knowledge_steward.profile.yaml`: project knowledge upkeep profile.
- `presets/*.preset.yaml`: common operating modes.
- `prompts/*.system.md`: reusable prompt fragments.
