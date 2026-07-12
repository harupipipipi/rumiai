# Interfaces

## Flows

This pack declares no flows.

## Functions and Handlers

This pack declares no executable functions or handlers. Capability names in `catalog/capabilities.workspace.json` and tool entries in `catalog/tools.workspace.json` are interface contracts only.

## Routes

This pack declares no HTTP routes or local API routes.

## Events

The pack names event-like lifecycle states in catalog metadata, but does not publish or subscribe to events. Suggested states include `drafted`, `rendered`, `reviewed`, `exported`, and `job_completed`.

## Stores

No store is required. Implementations that materialize artifacts should use runtime-approved workspace storage and preserve editability where possible.

## Required Secrets

`required_secrets` is empty. The pack must remain free of embedded credentials, service tokens, endpoint-specific bearer values, and provider keys.

## Network

Network access is `none_by_default`. Individual runtime implementations may request network grants for research, cloud export, or connector sync, but those grants are outside this pack.

## Grants

The catalog uses declarative grant names to let other packs reason about risk:

- `workspace.read`
- `workspace.write`
- `artifact.preview`
- `artifact.export`
- `job.enqueue`
- `job.status`

The pack itself does not request grants at install time.

## Catalog Files

- `catalog/capabilities.workspace.json`: named capabilities and their expected inputs, outputs, grants, and risk levels.
- `catalog/tools.workspace.json`: tool surface catalog for document, slide, sheet, chart, PDF, export, and job operations.
- `catalog/artifact_types.workspace.yaml`: artifact type taxonomy and lifecycle states.
- `catalog/export_targets.workspace.yaml`: export formats, file extensions, and fidelity expectations.
- `catalog/job_recipes.workspace.yaml`: inert background job recipes for repeatable workspace tasks.
