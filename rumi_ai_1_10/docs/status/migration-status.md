# Migration Status

Last updated: 2026-07-10

## `defaults` -> `defaultspack`

- Canonical prefix: `defaultspack.`
- Compatibility prefix: `defaults.`
- Compatibility aliases are tracked in `ecosystem/defaultspack/compat_aliases.yaml`.

Status:
- Canonical naming exists broadly across generated function manifests.
- Legacy aliases remain for compatibility and are explicitly allowlisted.

## Handwritten API -> `api_routes`

- Control-panel API routes are manifest-driven.
- Shared system GET routes are now declared in `core_runtime/core_pack/core_system_api/ecosystem.json`.
- `PackAPIHandler.do_GET()` now relies on route dispatch for core system routes before pack-route fallback.

Status:
- Major route families are already table-driven.
- Some transport-specific and migration-specific branches still remain in verb handlers.

## HTTP block route -> function route

- defaultspack transport route specs now expose canonical `function_id` / `legacy_block_module` metadata.
- Legacy HTTP fallbacks are tracked in `ecosystem/defaultspack/docs/legacy_http_routes.yaml`.
- Integrity scanning now checks function artifacts and legacy fallback allowlisting together.

Status:
- Many block-backed routes can now resolve through a function boundary first.
- Some routes remain explicit legacy fallbacks until replacement functions exist.

## Implicit domain imports -> declared boundaries

- defaultspack domain import policy now lives in `ecosystem/defaultspack/domain_boundaries.yaml`.
- `scripts/quality/scan_defaultspack_boundaries.py` checks cross-domain imports against that policy.
- `ecosystem/defaultspack/docs/domain-boundaries.md` defines pack contracts, domain contracts, and the intentional target dependency map.

Status:
- Domain-level edges and exact public-module edges are enforced in CI.
- The first narrowed edges cover chat IR/schema consumers and capability catalog consumers; remaining broad edges are migration debt rather than precedent for new imports.
