# defaultspack Data Model

`defaultspack` が扱う主な永続データと state の入口を整理します。

## Main Data Areas

- chat data: conversation / message / export 系 state
- memory data: memory, vector store, project context
- setup-pack data: setup pack selection, grant state, migration status
- module data: module catalog, enabled/disabled/degraded state
- shared configuration: prompts, agents, tools, ai model profiles, frontend extensions

## Where Data Lives

- runtime / user data 側: `user_data/`
- Pack bundled defaults: `ecosystem/defaultspack/user_data/shared/`
- function / backend migration helpers: `backend/migration/`, `functions/run_migration/`

## Documentation Links

- chat persistence と message surface: [chat.md](./chat.md)
- memory / knowledge: [memory.md](./memory.md), [concepts.md](./concepts.md)
- migration and compatibility: [migration.md](./migration.md)

## Change Rule

conversation schema, memory storage, setup-pack state, module state のいずれかを変える PR は、この doc と migration doc の更新を必須にします。
