<!-- docs-i18n-links:start -->
[EN](./rumi_bundle.md) | [JP](./i18n/ja/rumi_bundle.md) | [KR](./i18n/ko/rumi_bundle.md) | [CN](./i18n/zh-cn/rumi_bundle.md)
<!-- docs-i18n-links:end -->

# rumi_bundle

`rumi_bundle` is a standalone frontend bundle included in `defaultspack`.

Start `defaultspack/desktop_app.py` from `desktop_app` in `defaultspack/ecosystem.json` and open `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}` using the environment variables received from pack-shell. The default is `RUMI_DEFAULTSPACK_SURFACE=webview`, which opens as a native WebView app if pywebview is available. In environments without pywebview, it will fall back to browser display.

## Location

- `extensions/ui/rumi_bundle/manifest.json`
- `frontend/ui/rumi_bundle/module.json`

## Information we currently have

- `bundle_id`: `rumi_bundle`
- `pack_id`: `defaultspack`
- `launch_mode`: `desktop_app`
- `entry_url`: `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}`
- `port_source.default`: `8766`
- `app.icon`: `/static/assets/icons/defaultspack-icon.png`
- `parts`: `app_chrome`, `conversation_history`, `ai_chat`, `activity_preview`, `extension_sidebar`, `settings`
- `component_bindings`: `ai_chat` uses `chat` and requires `ai_client`
- `diagnostics`: Return malformed frontend contract as a warning

## Idea of division

The visible areas of the frontend are divided into `webapp/src/renderers/`. Render only known renderers or trusted local renderer bundles according to `parts`, `component_bindings`, `shell.layout`, `shell.renderers` received from `/api/ui/catalog`.

Even if you want to clean up the appearance, you can replace the same backend component with a different UI by leaving the contract between `extensions/ui/rumi_bundle/manifest.json` and `user_data/shared/frontend_extensions/*.ui.json`.
