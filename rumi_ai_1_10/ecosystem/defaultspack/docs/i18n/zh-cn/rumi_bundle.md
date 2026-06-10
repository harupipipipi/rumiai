<!-- docs-i18n-links:start -->
[EN](../../rumi_bundle.md) | [JP](../ja/rumi_bundle.md) | [KR](../ko/rumi_bundle.md) | [CN](./rumi_bundle.md)
<!-- docs-i18n-links:end -->

# 鲁米_bundle

`rumi_bundle` 是`defaultspack` 中包含的独立前端捆绑包。

从`defaultspack/ecosystem.json`中的`desktop_app`启动`defaultspack/desktop_app.py`，并使用从pack-shell接收的环境变量打开`http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}`。默认值为`RUMI_DEFAULTSPACK_SURFACE=webview`，如果 pywebview 可用，它将作为本机 WebView 应用程序打开。在没有 pywebview 的环境中，它将回退到浏览器显示。

## 位置

- §鲁米§0§
- §鲁米§0§

## 我们目前掌握的信息

- §鲁米§0§：§鲁米§1§
- §鲁米§0§：§鲁米§1§
- §鲁米§0§：§鲁米§1§
- §鲁米§0§：§鲁米§1§
- §鲁米§0§：§鲁米§1§
- §鲁米§0§：§鲁米§1§
- `parts`：`app_chrome`，`conversation_history`，`ai_chat`，`activity_preview`，`extension_sidebar`，`settings`
- `component_bindings`：`ai_chat`使用`chat`并需要`ai_client`
- `diagnostics`：返回格式错误的前端合约作为警告

## 划分思路

前端的可见区域分为`webapp/src/renderers/`。根据从`/api/ui/catalog`收到的`parts`、`component_bindings`、`shell.layout`、`shell.renderers`仅渲染已知渲染器或可信本地渲染器包。

即使您想清理外观，也可以通过保留`extensions/ui/rumi_bundle/manifest.json`和`user_data/shared/frontend_extensions/*.ui.json`之间的约定，用不同的UI替换相同的后端组件。
