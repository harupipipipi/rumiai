# defaultspack Interfaces

`defaultspack` の外から見える面を一枚にまとめた一覧です。

## Flows

- `simple_chat`: 会話作成、送信、履歴取得などの chat surface
- `agent_chat`: agent 実行、承認、拒否、状態確認
- `planning_agent`: planning 系の実行と状態確認

Flow 実装と entrypoint は [flows.md](./flows.md) を参照してください。

## Functions

`functions/` 配下の canonical surface:

- `list_modules`, `get_module`, `set_module_state`
- `list_setup_packs`, `install_setup_pack`
- `grant_all_ok`, `revoke_all_ok`
- `get_migration_status`, `run_migration`
- `list_pack_requests`, `get_pack_request`
- `request_extension`, `forced_patch`, `review_pack_request`, `rollback_pack_request`

詳細は [functions.md](./functions.md) を参照してください。

## Handlers

`ecosystem.json` で公開される主要 handler 群:

- `defaults.chat.*`
- `defaults.agent.*`
- `defaults.coding.*`
- `defaults.ai.*`
- `defaults.tool.*`
- `defaults.prompt.*`
- `defaults.memory.*`
- `defaults.knowledge.*`
- `defaults.media.*`
- `defaults.frontend.*`
- `defaults.dev.*`

handler 実装は主に `blocks/`、ドメイン実装は `domain/`、v2 移行面は `backend/` と `functions/` にあります。

## Routes And Events

- `routes.json`: `/api/packs/defaultspack/*` の Flow 連携 surface
- `ecosystem.json` の `api_routes`: `/api/defaultspack/*` と `/api/setup/*` の function-first surface
- frontend registry API と standalone UI surface: [frontend.md](./frontend.md), [frontend_extensions.md](./frontend_extensions.md)

API 詳細は [api.md](./api.md) を参照してください。

## Stores And Persistent Data

主な永続データ:

- chat conversation / message data
- memory / vector store data
- setup-pack selection と migration 状態
- module catalog / module state
- shared prompts, agents, tools, ai models

詳細は [data-model.md](./data-model.md) を参照してください。

## Required Runtime Contracts

- required secrets: AI provider 利用時の `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` など
- required network: AI provider や外部 integration を使う場合の outbound network
- required grants / permissions: `permissions.json` の `defaults.*` と `filesystem.read`, `filesystem.write`, `network.outbound`

runtime 共通ルールは [../../../docs/operations.md](../../../docs/operations.md) と [../../../docs/pack-documentation-contract.md](../../../docs/pack-documentation-contract.md) を参照してください。
