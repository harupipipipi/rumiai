# Interfaces

## Flows

This pack does not add executable flows or modifiers. Presets reference declarative analysis loops and recipe specs only.

## Functions And Handlers

This pack does not add functions, handlers, Python entrypoints, notebooks, SQL runners, or tool manifests.

## Routes

This pack does not add HTTP, WebSocket, desktop, CLI, or frontend routes.

## Events

The pack defines logical event names for consumers that choose to map them:

- `data.intake.created`
- `data.profile.completed`
- `data.cleaning_recipe.proposed`
- `data.analysis.completed`
- `data.chart_spec.created`
- `data.audit.completed`
- `data.workspace_handoff.ready`

No event handlers are registered by this pack.

## Stores

No stores are created. Consumers may persist recipes, audit trails, chart specs, and result tables through existing project, memory, artifact, or workspace stores.

## Required Secrets

None.

The pack must not contain API keys, database passwords, connection strings with credentials, OAuth secrets, private URLs, account tokens, or vendor keys.

## Network

Network default: `none`.

Profiles and presets assume local data. If a runtime adds remote warehouse, cloud sheet, or web download capabilities, those must be granted and audited outside this pack.

## Grants

No grants are required by this pack itself. Runtime execution may require grants from underlying packs for file reads, calculations, notebook or terminal execution, SQL access, browser use, or file writes.

## Workspace Pack Boundary

`rumi_workspace_pack` complements this pack. This pack owns analysis logic and reproducibility artifacts. Workspace owns final office deliverables and export lifecycle. The handoff payload should include:

- analysis summary
- data provenance
- cleaning recipe
- chart specs
- result tables
- audit notes
- limitations
