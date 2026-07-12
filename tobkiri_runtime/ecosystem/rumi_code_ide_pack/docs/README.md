# Rumi Code IDE Pack Docs

This directory contains pack-specific documentation for `rumi_code_ide_pack`.

## Reading Guide

- [architecture.md](architecture.md): responsibilities, directory layout, execution model, and runtime boundaries.
- [interfaces.md](interfaces.md): profiles, prompts, presets, command recipes, tool scopes, dependencies, grants, secrets, network, and overlap notes.
- [operations.md](operations.md): install expectations, development workflow, tests, and common failure modes.

## First-Time Orientation

This pack is intentionally declarative. It adds opinionated coding workflows on top of existing Rumi primitives from `defaultspack` and concrete tools from `rumi_default_tools_pack`. Treat it as an optional customization layer for advanced coding sessions, not as the owner of core coding capabilities.
