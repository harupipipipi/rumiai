# Rumi Model Evals Pack Docs

These docs describe the model-evaluation pack boundary, declared interfaces, and operating rules.

## Reading Guide

1. Read [architecture.md](architecture.md) for responsibilities and runtime boundaries.
2. Read [interfaces.md](interfaces.md) for flows, routes, events, stores, grants, secrets, and network posture.
3. Read [operations.md](operations.md) before adding eval specs, recipes, presets, or setup metadata.

## Pack Areas

- `catalog/`: model-eval capability and provider-evidence catalog overlays.
- `specs/`: layered eval contract, metrics, fit matrix, and promotion gate schemas.
- `recipes/`: declarative recipes for provider smoke, pass@k, flakiness, routing, and promotion evidence.
- `profiles/`: local-first model-eval roles.
- `prompts/`: system prompt contracts for eval roles.
- `presets/`: user-facing model-eval and routing modes.
- `examples/`: concrete local-first eval task declarations.

This pack is deliberately declarative. Runtime execution belongs to approved provider tooling, defaultspack, or a future implementation pack.
