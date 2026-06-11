# Rumi Prompt Studio Pack

Rumi Prompt Studio Pack is a declarative setup pack for prompt artifacts and prompt review rules. It provides a prompt library, lint rubrics, reusable persona and style presets, custom instruction migration guidance for Claude, ChatGPT, and Gemini, plus local fixture dry runs that can be reviewed without network access.

Required Secrets: None.

Required Network: None.

This pack depends on `defaultspack` for loading and runtime ownership. It does not benchmark models, route models, store memory, create tools, create APIs, or execute remote runs. When a prompt requires runtime behavior, the handoff goes to the owning runtime or integration pack.

## What It Owns

- Prompt catalog entries and prompt artifact schema.
- Prompt linting rubrics and blocking review rules.
- Persona and style presets that can be reused by other packs.
- Migration records for custom instructions copied from Claude, ChatGPT, and Gemini.
- Local fixture dry-run cases and review ledger schema.

## What It Does Not Own

- Model choice, model routing, model scoring, or benchmark claims.
- Memory stores, saved preferences, user profile persistence, or embeddings.
- Tool schemas, APIs, plugins, runtime functions, or host execution.
- Production telemetry or remote evaluation pipelines.

## Main Artifacts

- `catalog/prompt_library.yaml` defines reusable prompt entries with slots, review intent, fixtures, and lint focus.
- `catalog/prompt_lint_rubrics.yaml` defines criteria for instruction hierarchy, boundary clarity, testability, migration fidelity, style clarity, and privacy.
- `catalog/custom_instruction_migration_map.yaml` explains how to translate Claude, ChatGPT, and Gemini instruction surfaces into Rumi prompt artifacts.
- `catalog/style_persona_catalog.yaml` describes persona/style presets without storing user memory.
- `catalog/local_fixture_dry_runs.yaml` declares static dry-run cases that exercise the fixtures.
- `ledgers/prompt_studio_review_ledger.schema.yaml` captures evidence for prompt release review.

## Promotion Boundary

The setup metadata marks defaultspack promotion as blocked. This is intentional. Prompt Studio is useful beside defaultspack, but it is not a replacement for runtime setup, model routing, memory, tools, APIs, or execution.
