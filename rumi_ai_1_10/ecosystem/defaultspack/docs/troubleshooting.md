# defaultspack Troubleshooting

## Standalone UI Does Not Start

- `DEFAULTS_HTTP_PORT` の競合を確認する
- `blocks/frontend/start.py` に `facade` が渡っているか確認する
- `webapp` を触った直後なら `npm run build` 済みか確認する

## AI Response Falls Back To Stub

- provider API key が入っているか確認する
- `model` が有効な provider/model 名になっているか確認する
- 関連 docs: [ai_client.md](./ai_client.md), [ai-providers.md](./ai-providers.md)

## Module Or Setup-Pack APIs Break

- `/api/defaultspack/*` route が `ecosystem.json` の `api_routes` と一致しているか確認する
- function id と `functions/<id>/manifest.json` / `main.py` の対応を確認する
- migration 状態が影響していないか [migration.md](./migration.md) を確認する

## Frontend Extension UI Is Missing

- registry contract と renderer 実装が両方更新されているか確認する
- 関連 docs: [frontend.md](./frontend.md), [frontend_extensions.md](./frontend_extensions.md)
