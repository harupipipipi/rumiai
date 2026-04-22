# defaultspack Migration

legacy defaults から `defaultspack` へ移行するときの canonical 入口です。

## Current Canonical Rules

- production routing は `/api/defaultspack/*` を正とする
- setup-pack install と migration status は function-first surface を使う
- 新規機能は `functions/` と pack-local docs を正とする

## Main Compatibility Topics

- legacy `ecosystem/defaults` は reference / compat として残りうる
- `user.csv` から `user.json` への移行補助がある
- module rollback / disable による fail-soft recovery を前提にする

## Legacy Docs

- old root stub: [../../../docs/defaultspack_migration.md](../../../docs/defaultspack_migration.md)
- old root guide: [../../../docs/migration-guide.md](../../../docs/migration-guide.md)
