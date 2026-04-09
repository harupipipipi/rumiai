# defaultspack v2

`defaultspack` is now a tracked first-class pack under `ecosystem/defaultspack/`.

## What changed

- Canonical backend API paths now live under `/api/defaultspack/*`.
- Setup-pack discovery comes from `ecosystem/setup_pack/*/pack.json`.
- Module state is cataloged and persisted by `core_runtime/defaultspack_manager.py`.
- Defaultspack operations are executed through `functions/` instead of direct block imports.

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
- `GET /api/defaultspack/setup/packs`
- `POST /api/defaultspack/setup/packs/install`
- `POST /api/defaultspack/setup/packs/{id}/grant-all-ok`
- `POST /api/defaultspack/setup/packs/{id}/revoke-all-ok`
- `GET /api/defaultspack/migration/status`
