# defaultspack Functions

`defaultspack` v2 の function-first surface をまとめます。

## Module Management

- `list_modules`
- `get_module`
- `set_module_state`

対象 route:

- `GET /api/defaultspack/modules`
- `GET /api/defaultspack/modules/{id}`
- `POST /api/defaultspack/modules/{id}/enable`
- `POST /api/defaultspack/modules/{id}/disable`
- `POST /api/defaultspack/modules/{id}/reload`
- `POST /api/defaultspack/modules/{id}/rollback`

## Setup Pack And Migration

- `list_setup_packs`
- `install_setup_pack`
- `grant_all_ok`
- `revoke_all_ok`
- `get_migration_status`
- `run_migration`

## Pack Request Workflow

- `list_pack_requests`
- `get_pack_request`
- `request_extension`
- `forced_patch`
- `review_pack_request`
- `rollback_pack_request`

## Implementation Map

- contract source: `ecosystem.json` の `api_routes`
- implementation: `functions/<function_id>/main.py`
- manifest: `functions/<function_id>/manifest.json`

breaking change や compatibility は [migration.md](./migration.md) を参照してください。
