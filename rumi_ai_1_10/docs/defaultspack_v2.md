# defaultspack v2

`defaultspack` is now a tracked first-class pack under `ecosystem/defaultspack/`.

## What changed

- Canonical backend API paths now live under `/api/defaultspack/*`.
- Setup-pack discovery comes from `ecosystem/setup_pack/*/pack.json`.
- Module state is cataloged and persisted by defaultspack backend module helpers.
- Defaultspack operations are executed through `functions/` instead of direct block imports.
- Pack modification requests now enforce slot/fullscreen conflict rules before approval.
- Legacy CLI/HTTP fallback transports dispatch through `bridge/block_adapter.py` instead of importing block handlers directly.

## Module model

Each module exposes:

- `enabled`
- `disabled`
- `degraded`
- `error_disabled`
- `experimental`

Dependency failures degrade dependents without taking down the whole pack.

## Main endpoints

- `GET /api/defaultspack/modules`
- `GET /api/defaultspack/modules/{id}`
- `POST /api/defaultspack/modules/{id}/enable`
- `POST /api/defaultspack/modules/{id}/disable`
- `POST /api/defaultspack/modules/{id}/reload`
- `POST /api/defaultspack/modules/{id}/rollback`
- `GET /api/setup/packs`
- `POST /api/setup/packs/install`
- `POST /api/setup/packs/{id}/grant-all-ok`
- `POST /api/setup/packs/{id}/revoke-all-ok`
- `GET /api/setup/migration/status`
- `GET /api/defaultspack/pack-requests`
- `POST /api/defaultspack/pack-requests/request-extension`
- `POST /api/defaultspack/pack-requests/forced-patch`
- `POST /api/defaultspack/pack-requests/{id}/approve`
- `POST /api/defaultspack/pack-requests/{id}/reject`
- `POST /api/defaultspack/pack-requests/{id}/rollback`

## Setup flow

The setup UI under `/setup` asks whether each discovered setup pack should be included at startup.
Selected setup packs are installed together and receive `all OK` grants from setup.

## Pack modification flow

Pack changes can be staged first, then submitted as either:

- `request_extension`
- `forced_patch`

Both produce an approval-backed request record before any apply occurs.

Conflict policy:

- fullscreen requests are exclusive across active pending/applied requests
- exclusive requests cannot share the same slot
- non-exclusive same-slot frontend requests are preserved, but flagged for explicit active selection
