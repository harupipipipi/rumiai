# Architecture

## Responsibility

`rumi_memory_knowledge_pack` defines local-first memory and knowledge contracts for Rumi. It describes how agents should reason about session recall, user profile memory, project knowledge, skill-learning proposals, memory hygiene, and evidence-backed recall.

The pack is inspired by Hermes-style persistent memory, session search, skill creation, self-improvement, cron-triggered routines, and messaging continuity, plus Cline/OpenClaw-style project rules, session state, and skills. In Rumi, this pack stays declarative: it does not implement memory storage or mutation.

The pack covers:

- Memory object schemas and evidence fields.
- Recall workflows and confidence rules.
- User profile and project knowledge boundaries.
- Skill-learning proposal contracts.
- Hygiene policies for stale, duplicated, contradicted, or sensitive memories.

The pack does not own:

- Runtime memory writes, deletion, indexes, embeddings, or search engines.
- Cron scheduling, messaging gateways, or long-running jobs.
- Research evidence collection.
- Default runtime boot behavior.

## Main Directories

- `catalog/`: capability and workflow catalogs for memory and knowledge surfaces.
- `specs/`: memory object, evidence, and skill proposal schemas.
- `policies/`: hygiene, recall evidence, retention, and skill-learning policies.
- `profiles/`: runtime profile declarations for curation and recall review modes.
- `presets/`: task modes that combine profiles, panels, and behavior hints.
- `prompts/`: system prompt fragments for memory curation and evidence-backed recall.
- `examples/`: synthetic task examples for session recall, project knowledge, and skill-learning proposals.
- `docs/`: pack-specific documentation required by the shared pack contract.

## Execution Path

1. The setup selector discovers `ecosystem/setup_pack/rumi_memory_knowledge_pack/pack.json`.
2. Rumi loads `ecosystem/rumi_memory_knowledge_pack/ecosystem.json`.
3. Runtime or UI surfaces may read catalogs, specs, policies, profiles, presets, prompts, and examples as data.
4. A concrete memory implementation decides whether it can satisfy capability names such as `memory.recall.session`, `memory.profile.propose_update`, or `memory.skill.propose`.
5. Any actual write must go through the runtime implementation's own approval, storage, and audit path.

## Runtime Touch Points

- `defaultspack`: already contains local memory-related runtime surfaces. This pack adds declarative contracts and must not replace those surfaces.
- `rumi_local_agent_pack`: contains local agent prompts/profiles that may consume memory guidance. This pack does not own local-agent execution.
- `rumi_agent_services_pack`: may schedule memory hygiene routines or background curation. This pack only defines policies and routine recipes.
- `rumi_research_pack`: may provide evidence records for recall. This pack owns memory recall contracts, not research collection.
