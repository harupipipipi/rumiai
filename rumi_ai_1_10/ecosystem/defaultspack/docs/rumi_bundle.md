# rumi_bundle

`rumi_bundle` は `defaultspack` に同梱する standalone frontend bundle です。

`defaultspack/ecosystem.json` の `desktop_app` から `defaultspack/desktop_app.py` を起動し、pack-shell から受け取った環境変数を使って `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}` を開きます。

## 置き場所

- `extensions/ui/rumi_bundle/manifest.json`
- `frontend/ui/rumi_bundle/module.json`

## いま持っている情報

- `bundle_id`: `rumi_bundle`
- `pack_id`: `defaultspack`
- `launch_mode`: `desktop_app`
- `entry_url`: `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}`
- `port_source.default`: `8766`
- `app.icon`: `/static/assets/icons/defaultspack-icon.png`
- `parts`: `ai_chat`, `activity_preview`
- `component_bindings`: `ai_chat` が `chat` を使い、`ai_client` を要求する

## 分割の考え方

frontend は component を直接 import しません。`/api/ui/catalog` から受け取る `parts` と `component_bindings` に従い、知っている renderer だけを描画します。

見た目を一掃する場合も、`extensions/ui/rumi_bundle/manifest.json` と `user_data/shared/frontend_extensions/*.ui.json` の契約を残せば、同じ backend component を別 UI に載せ替えられます。
