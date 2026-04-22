# defaultspack migration notes

> **Legacy stub**: canonical migration docs は [../ecosystem/defaultspack/docs/migration.md](../ecosystem/defaultspack/docs/migration.md) に移しました。

要点だけ残します。

- production routing は `/api/defaultspack/*` を正とする
- 新規機能は `ecosystem/defaultspack/functions/*` を優先する
- rollback / disable / revoke-all-ok の運用は pack-local migration docs を参照する
