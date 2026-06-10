<!-- docs-i18n-links:start -->
[EN](../../rumi_bundle.md) | [JP](./rumi_bundle.md) | [KR](../ko/rumi_bundle.md) | [CN](../zh-cn/rumi_bundle.md)
<!-- docs-i18n-links:end -->

# rumi_bundle

`rumi_bundle` は `defaultspack` に同梱する standalone frontend bundle です。

`defaultspack/ecosystem.json` の `desktop_app` から `defaultspack/desktop_app.py` を起動し、pack-shell から受け取った環境変数を使って `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}` を開きます。既定は `RUMI_DEFAULTSPACK_SURFACE=webview` で、pywebview が利用できる場合は native WebView アプリとして開きます。pywebview が無い環境ではブラウザ表示へフォールバックします。

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
- `parts`: `app_chrome`, `conversation_history`, `ai_chat`, `activity_preview`, `extension_sidebar`, `settings`
- `component_bindings`: `ai_chat` が `chat` を使い、`ai_client` を要求する
- `diagnostics`: malformed frontend contract を警告として返す

## 分割の考え方

frontend の visible areas は `webapp/src/renderers/` に分割されています。`/api/ui/catalog` から受け取る `parts`, `component_bindings`, `shell.layout`, `shell.renderers` に従い、知っている renderer または trusted local renderer bundle だけを描画します。

見た目を一掃する場合も、`extensions/ui/rumi_bundle/manifest.json` と `user_data/shared/frontend_extensions/*.ui.json` の契約を残せば、同じ backend component を別 UI に載せ替えられます。
