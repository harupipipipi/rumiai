<!-- docs-i18n-links:start -->
[EN](../../rumi_bundle.md) | [JP](../ja/rumi_bundle.md) | [KR](./rumi_bundle.md) | [CN](../zh-cn/rumi_bundle.md)
<!-- docs-i18n-links:end -->

#rumi_bundle

`rumi_bundle`는 `defaultspack`와 함께 제공되는 standalone frontend bundle입니다.

`defaultspack/ecosystem.json`의 `desktop_app`에서 `defaultspack/desktop_app.py`를 시작하고 pack-shell에서 받은 환경 변수를 사용하여 `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}`를 엽니다. 기본값은 `RUMI_DEFAULTSPACK_SURFACE=webview`이며 pywebview를 사용할 수 있는 경우 native WebView 앱으로 엽니다. pywebview가 없는 환경에서는 브라우저 표시로 폴백합니다.

## 위치

- `extensions/ui/rumi_bundle/manifest.json`
- `frontend/ui/rumi_bundle/module.json`

## 지금 가지고있는 정보

- `bundle_id`: `rumi_bundle`
- `pack_id`: `defaultspack`
- `launch_mode`: `desktop_app`
- `entry_url`: `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}`
- `port_source.default`: `8766`
- `app.icon`: `/static/assets/icons/defaultspack-icon.png`
- `parts`: `app_chrome`, `conversation_history`, `ai_chat`, `activity_preview`, `extension_sidebar`, `settings`
- `component_bindings`: `ai_chat`가 `chat`를 사용하고 `ai_client`를 요청합니다.
- `diagnostics`: malformed frontend contract를 경고로 반환

## 분할 아이디어

frontend의 visible areas는 `webapp/src/renderers/`로 나뉩니다. `/api/ui/catalog`에서 받는 `parts`, `component_bindings`, `shell.layout`, `shell.renderers`에 따라 알고 있는 renderer 또는 trusted local renderer bundle만을 그립니다.

외형을 지우는 경우에도 `extensions/ui/rumi_bundle/manifest.json`와 `user_data/shared/frontend_extensions/*.ui.json`의 계약을 남겨두면 동일한 backend component를 다른 UI에 넣을 수 있습니다.
