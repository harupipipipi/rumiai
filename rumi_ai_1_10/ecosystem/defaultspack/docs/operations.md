# defaultspack Operations

`defaultspack` を起動・開発・検証するときの運用入口です。

## Run

- standalone 起動と最初の確認: [getting-started.md](./getting-started.md)
- viewer 経由の起動導線: [../../../docs/rumi_viewer_start.md](../../../docs/rumi_viewer_start.md)
- runtime 共通の起動 / health / secrets: [../../../docs/operations.md](../../../docs/operations.md)

## Development

- frontend source: `webapp/`
- build 済み asset 配信先: `ui/`
- handler entrypoints: `blocks/`
- function-first v2 surface: `functions/`
- domain / backend internals: `domain/`, `backend/`

## Tests

代表的な確認:

```bash
python -m pytest tests/test_defaultspack_modules.py
python -m pytest tests/test_defaultspack_google_provider.py
python -m pytest tests/test_defaultspack_ui_registry.py
```

frontend を触ったときの追加確認:

```bash
cd ecosystem/defaultspack/webapp
npm run lint
npm run build
```

## Common Failure Modes

- `DEFAULTS_HTTP_PORT` 競合で standalone frontend が上がらない
- API key 未設定で AI 呼び出しが stub/fallback になる
- frontend registry と renderer 実装がずれて UI が欠ける
- module state / setup-pack migration の変更で `/api/defaultspack/*` surface が崩れる

## Change Checklist

- flow / function / route を追加したら [interfaces.md](./interfaces.md) と該当 docs を更新する
- required secrets / grants / network が変わったら [interfaces.md](./interfaces.md) と [security.md](./security.md) を更新する
- data model を変えたら [data-model.md](./data-model.md) と [migration.md](./migration.md) を更新する
- frontend contract を変えたら [frontend.md](./frontend.md) と [frontend_extensions.md](./frontend_extensions.md) を更新する
