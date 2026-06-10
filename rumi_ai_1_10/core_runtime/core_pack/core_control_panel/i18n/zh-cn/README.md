<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 核心控制面板

该面板的规范前端源位于`../../../../../rumi_viewer/frontend`。

该包提供来自`web/`的`/panel`处的内置静态工件。浏览器路由 (`http://127.0.0.1:8765/panel/`) 和 Rumi 查看器引导流程都使用相同的工件。

Tauri `splash` 屏幕保持独立，仅在内核准备就绪之前使用。
