# defaultspack Security

`defaultspack` は runtime の capability / grant モデルの上で動きます。root の runtime ルールを前提にしつつ、この Pack 固有の注意点だけをまとめます。

## Trust Surface

- self permissions: `permissions.json`
- handler allow presets: `full_access`, `chat_only`, `coding_only`, `readonly`, `agent`
- function-first APIs: module 管理、setup-pack install、pack request workflow

## Sensitive Areas

- `grant_all_ok` / `revoke_all_ok`
- setup-pack install
- module enable / disable / rollback
- coding handlers と外部 AI provider 呼び出し

## Required Review Points

- required grants が増えていないか
- filesystem / network 使用面が広がっていないか
- setup-pack or module APIs が approval flow を飛ばしていないか
- frontend extension surface が untrusted input をそのまま render していないか

runtime 全体の approval / grant / kernel ルールは [../../../docs/architecture.md](../../../docs/architecture.md) と [../../../docs/operations.md](../../../docs/operations.md) を参照してください。
