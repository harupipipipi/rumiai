# Rumi Agent Services Pack Docs

Use these docs when adding, reviewing, or operating the agent-services pack.

## Reading Guide

1. Read [architecture.md](architecture.md) to understand the pack boundary and directory responsibilities.
2. Read [interfaces.md](interfaces.md) to see what the pack declares and what it does not expose.
3. Read [operations.md](operations.md) before changing setup metadata, profiles, prompts, or workflow specs.

## Pack Files

- `profiles/`: role-specific runtime profile declarations.
- `prompts/`: system prompt contracts for service roles.
- `presets/`: named service experiences inspired by modern agent tools.
- `coordination/`: routing, workflow, and handoff specs.
- `catalog/`: capability names and local-first requirements.
- `examples/`: concrete task declarations for pack consumers.

This pack is intentionally declarative. If executable behavior is needed, add it to an implementation pack rather than this service-shape pack.
