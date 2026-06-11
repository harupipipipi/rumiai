<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](./i18n/ja/README.md) | [KR](./i18n/ko/README.md) | [CN](./i18n/zh-cn/README.md)
<!-- docs-i18n-links:end -->

# Core Control Panel

The canonical frontend source for this panel lives in `../../../../../rumi_viewer/frontend`.

This pack serves the built static artifact at `/panel` from `web/`. Both the browser route (`http://127.0.0.1:8765/panel/`) and the Rumi Viewer bootstrap flow use the same artifact.

The Tauri `splash` screen remains separate and is only used before the kernel is ready.
