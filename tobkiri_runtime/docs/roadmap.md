# Tobkiri Roadmap

`roadmap.md` is the forward-looking document.
Current implementation truth now lives under [`docs/status/`](status/current-status.md).

## North Star

Tobkiri should behave like a local-first runtime OS for packs:

- core runtime owns approval, trust, grants, isolation, audit, and transport boundaries
- ecosystem packs expose stable public boundaries through manifests, functions, and routed APIs
- defaultspack remains the canonical pack implementation, but not an unbounded monolith
- desktop surfaces should launch into a usable control panel without terminal-first setup

## Current Strategic Themes

### 1. Harden public execution boundaries

- keep `function_id` execution on the same approval / hash / trust / grant gates as other runtime entrypoints
- keep host-capable execution explicit, auditable, and narrow
- prefer manifest-driven routing over ad hoc call sites

### 2. Finish table-driven API migration

- move handwritten runtime API branches into `api_routes` manifests where practical
- keep `PackAPIHandler` focused on HTTP transport concerns and fallback orchestration
- preserve pre-auth, static web mounts, and control-panel flows without special-case sprawl

### 3. Make defaultspack migration status explicit

- treat `defaultspack.*` as canonical naming
- keep `defaults.*` only as tracked compatibility aliases
- route HTTP entrypoints toward function boundaries, with legacy fallbacks explicitly allowlisted
- enforce domain import boundaries with repo-owned policy files

### 4. Improve desktop-first product surfaces

- keep control panel / setup / viewer flows aligned with the current repo layout
- continue tightening viewer, desktop capability, and control-panel integration around the canonical runtime

## How To Read This

- For what is implemented now: [`docs/status/current-status.md`](status/current-status.md)
- For known debt and priority: [`docs/status/known-debt.md`](status/known-debt.md)
- For migration state across old/new boundaries: [`docs/status/migration-status.md`](status/migration-status.md)
