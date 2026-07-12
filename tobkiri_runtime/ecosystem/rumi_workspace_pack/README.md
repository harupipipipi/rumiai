# Rumi Workspace Pack

`rumi_workspace_pack` is an optional, mostly declarative ecosystem pack for workspace artifact work. It gives Rumi a product-shaped catalog for creating and operating on slides, sheets, docs, PDFs, charts, exports, and background job recipes without adding runtime handlers or embedding credentials.

## What It Provides

- Workspace profiles for artifact authoring and async workspace operations.
- Presets inspired by Genspark-style report generation and Manus-style long-running task execution.
- Prompt templates for artifact fidelity, export planning, review, and background jobs.
- Catalog files for artifact types, capability names, tool surfaces, export targets, and job recipes.
- Examples for research-to-deck workflows, spreadsheet dashboards, and business-review bundles.

## What It Does Not Provide

- No executable handlers, routes, daemons, or provider clients.
- No bundled secrets, credentials, external service tokens, or remote endpoints.
- No PDF, spreadsheet, slide, or document renderer implementation. This pack names interfaces that runtime packs or tool packs can implement.

## Docs

Start with [docs/README.md](docs/README.md). The pack follows the shared contract in `tobkiri_runtime/docs/pack-documentation-contract.md`.
