# Architecture

## Responsibility

`rumi_workspace_pack` defines a declarative workspace artifact layer for Rumi. It describes what artifact-oriented agents should know how to plan, create, review, export, and schedule, while leaving execution to existing runtime and tool packs.

The pack covers:

- Editable documents, slide decks, spreadsheets, PDFs, charts, and bundled exports.
- Agent profiles and presets for artifact-first work.
- Catalog entries that name capabilities, expected grants, and artifact lifecycle states.
- Background job recipes for repeatable asynchronous workspace tasks.

The pack does not own execution code. It is safe to install as an optional pack because it has no handlers, network clients, long-running processes, or local credential readers.

## Main Directories

- `catalog/`: JSON and YAML catalogs for capabilities, tool surfaces, artifact types, export targets, and job recipes.
- `profiles/`: runtime profile declarations for workspace artifact agents.
- `presets/`: higher-level task modes that combine profiles, panels, and behavior hints.
- `prompts/`: system prompt fragments for artifact fidelity, export planning, and async job execution.
- `examples/`: concrete task payloads that demonstrate expected workspace bundles.
- `docs/`: pack-specific documentation required by the pack documentation contract.

## Execution Path

1. The setup pack exposes `rumi_workspace_pack` to the selector.
2. Rumi discovers `ecosystem.json` and reads the declared catalog/profile components.
3. A runtime or UI surface can load `profiles/`, `presets/`, `prompts/`, and `catalog/` as data.
4. Concrete tool packs decide whether they can satisfy named capabilities such as `workspace.document.create`, `workspace.chart.render`, or `workspace.export.pdf`.
5. Background job recipes remain inert until a runtime job system maps them to real handlers.

## Runtime Touch Points

- `defaultspack` supplies the core runtime and graph/profile conventions.
- Optional tool packs can satisfy catalog capabilities with concrete implementations.
- UI packs may present workspace panels such as artifact tree, preview, export queue, and job timeline.
- No component in this pack requires a store, route, event bus, or network connection by itself.
