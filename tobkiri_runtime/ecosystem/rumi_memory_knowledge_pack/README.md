# Rumi Memory Knowledge Pack

`rumi_memory_knowledge_pack` is an optional declarative pack for local-first memory and knowledge contracts. It is inspired by agent systems that emphasize persistent memory, session search, skill creation, self-improvement, scheduled routines, and messaging continuity, but it keeps those ideas Rumi-native and data-only.

## What It Provides

- Contracts for session recall, user profile memory, project knowledge, and evidence-backed recall.
- Policies for memory hygiene, retention, deduplication, contradiction review, and sensitive-memory handling.
- Skill-learning proposal templates that let an agent suggest new skills without installing or editing them directly.
- Profiles and presets for memory curation, project knowledge upkeep, recall review, and skill proposal review.
- Examples for session recall, project knowledge updates, and skill-learning proposals.

## What It Does Not Provide

- No executable memory writer, vector index, search daemon, cron job, gateway, handler, route, or database migration.
- No runtime memory writes. This pack defines contracts and policies that runtime memory surfaces may implement.
- No secrets, provider keys, connector tokens, or private endpoints.
- No network by default. Local session transcripts, user-approved notes, and workspace artifacts are the intended inputs.

## Docs

Start with [docs/README.md](docs/README.md). This pack follows `tobkiri_runtime/docs/pack-documentation-contract.md`.
