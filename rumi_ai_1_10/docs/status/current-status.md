# Current Status

Last updated: 2026-07-10

## Implemented

- Core runtime approval, hash verification, trust store, grant manager, audit logging, and capability execution are in active use.
- Canonical runtime code lives in `rumi_ai_1_10/`.
- Canonical pack implementation lives in `ecosystem/defaultspack/`.
- Canonical control-panel frontend lives in `ecosystem/defaultspack/webapp/`.
- Desktop-facing runtime surfaces already exist in `core_control_panel`, `core_viewer_capability`, `core_desktop_capability`, `rumi_viewer/`, and related API handlers.
- `api_routes` table dispatch is already live for control-panel and pack-defined API endpoints.
- Builtin core API routes now also include `core_system_api`, so shared system GET routes load from manifest data instead of handwritten `do_GET` branches.
- Pack function invocation now runs through explicit execution policy checks before dispatch.

## Partial / In Progress

- `PackAPIHandler` is mostly decomposed into mixins, but the verb methods still coordinate multiple fallback paths in one file.
- defaultspack HTTP routes are in migration: many now resolve through functions or flows first, but legacy block fallbacks still exist and are now tracked explicitly.
- compatibility aliases under `defaults.*` still exist broadly for stability; they are tracked as compatibility, not canonical naming.
- defaultspack domain boundaries are declared and CI-enforced. The first intentional public-only edges now restrict `ai_client -> chat`, `tool -> chat`, and capability-catalog consumers to exact contract modules; remaining broad edges are tracked for incremental tightening.

## Planned Next Tightening

- reduce remaining handwritten API branches where manifest-driven routes are already sufficient
- continue shrinking legacy defaultspack HTTP fallbacks by replacing allowlisted block routes with direct function boundaries
- narrow compatibility aliases and domain exceptions over subsequent migrations
- replace understood broad `may_import` edges with exact `public_imports` contracts, following `ecosystem/defaultspack/docs/domain-boundaries.md`
- keep desktop/runtime docs aligned with actual shipped surfaces instead of historical plans
