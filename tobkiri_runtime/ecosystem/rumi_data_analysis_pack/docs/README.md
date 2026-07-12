# Rumi Data Analysis Pack Docs

These docs explain the pack boundary, declared interfaces, and operating rules.

## Reading Guide

1. Read [architecture.md](architecture.md) for the pack responsibility and directory map.
2. Read [interfaces.md](interfaces.md) for flows, routes, stores, network, secrets, and grant expectations.
3. Read [operations.md](operations.md) before adding profiles, prompts, presets, recipes, or setup metadata.

## Pack Areas

- `catalog/`: data shapes, analysis capabilities, and chart kind metadata.
- `profiles/`: role-specific local-first data analysis profiles.
- `prompts/`: system prompt contracts for analysis roles.
- `presets/`: user-facing analysis modes.
- `recipes/`: reproducible data cleaning and analysis recipe templates.
- `specs/`: chart and audit trail schemas.
- `examples/`: concrete local-first task declarations.

The pack is declarative by design. Runtime execution belongs to defaultspack, rumi_default_tools_pack, local agent profiles, or a future implementation pack.
