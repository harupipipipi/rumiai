# Migration Status

Last updated: 2026-07-10

## `defaults` -> `defaultspack`

- Canonical prefix: `defaultspack.`
- Compatibility prefix: `defaults.`
- Protocol v4 Pack and executable catalogs are the only runtime function authority.
- Legacy alias vocabulary and its migration history are documented in `docs/compat-alias-migration.md`.

Status:
- Canonical naming exists across generated function manifests.
- Legacy `defaults.*` resolution is outside the v4 runtime boundary.
- v4 generation and integrity checks use canonical Function identities and real implementation hashes.
- The verified-unused `defaults.model_runtime.*` group is not a v4 Function identity.

## Handwritten API -> `api_routes`

- Control-panel API routes are manifest-driven.
- Shared system GET routes are now declared in `core_runtime/core_pack/core_system_api/ecosystem.json`.
- `PackAPIHandler.do_GET()` now relies on route dispatch for core system routes before pack-route fallback.
- Remaining verb-handler and mixin families are inventoried in `docs/status/handwritten-route-inventory.md`.

Status:
- Major route families are already table-driven.
- Some transport-specific and migration-specific branches still remain in verb handlers.

## HTTP block route -> function route

- The v4 executable catalog exposes canonical Function identities and operation bindings.
- Legacy HTTP route metadata is an offline migration surface, not a v4 authority.
- Strict integrity scanning checks the v4 Pack, contracts, artifact index, executable catalog, bundle lock, and implementation hashes.
- The chat-channel compatibility family is not a v4 executable identity.

Status:
- Many block-backed routes can now resolve through a function boundary first.
- Some routes remain explicit legacy fallbacks until replacement functions exist.

## Implicit domain imports -> declared boundaries

- defaultspack domain import policy now lives in `ecosystem/defaultspack/domain_boundaries.yaml`.
- `scripts/quality/scan_defaultspack_boundaries.py` checks cross-domain imports against that policy.

Status:
- Baseline policy is captured and enforced.
- Tightening the policy is a follow-up migration, not finished work.
