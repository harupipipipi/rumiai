<!-- docs-i18n-links:start -->
[EN](../../../../examples/viewer_pack/README.md) | [JP](../../../ja/examples/viewer_pack/README.md) | [KR](../../../ko/examples/viewer_pack/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 查看器示例包

使用`viewer:display` 功能在 Rumi Viewer 中显示前端的 Pack 的最小示例。

## 概述

该包显示：

- `viewer.display` 如何声明能力（`manifest.json`、`requires` 和 `vocab_aliases`）
- 由`grant_config`授予设置
- 使用`web_mount`进行前端交付
- `calling_convention: "block"` 的函数存根

## 目录结构

```
viewer_pack/
├── ecosystem.json                    # Pack 定義（web_mount, functions）
├── functions/
│   └── request_display/
│       ├── manifest.json             # viewer.display capability 宣言
│       └── main.py                   # Function スタブ（block）
├── web/
│   ├── index.html                    # Pack フロントエンド
│   └── style.css                     # スタイル
└── README.md                         # このファイル
```

## 各个文件的作用

### 生态系统.json

包的清单。定义`pack_id`、`metadata`、`web_mount`、`functions`。
`web_mount` 字段提供 Rumi 查看器中`web/` 目录的内容。

### 函数/request_display/manifest.json

`viewer.display` 详细的能力声明。以下字段很重要：

- **`requires`**：`["viewer.display"]` — 此功能所需的能力
- **`vocab_aliases`**：`["viewer.display"]` — 用于 FunctionRegistry 中的别名解析
- **`grant_config`**：拨款设置（`allowed_packs`、`max_token_lifetime`）
- **`calling_convention`**：`"block"` — 通过内核的 DI 处理程序执行

### 函数/request_display/main.py

这是`calling_convention: "block"`的存根。运行时的内核 DI 处理程序
(`handle_display`)，因此该文件永远不会直接执行。
存在是为了 Pack 结构的完整性。

### web/index.html, web/style.css

这是 Pack 的前端。加载到 Rumi Viewer 的沙箱 WebView 中。
我不使用 CDN 并用纯 HTML/CSS 编写它。

## 查看器：显示功能如何工作

1. 包请求`viewer.display`能力
2.`capability_executor`由`FunctionRegistry.resolve_by_alias("viewer.display")`解决
3. 如果设置了`grant_config`，则`capability_grant_manager`检查Grant
4. `calling_convention: "block"` → 内核 DI 处理程序 (`handle_display`) 执行
5. 代币和`web_mount_url`将被退回
6. Rumi Viewer 将`web_mount_url`加载到沙盒WebView中

## 获得资助

该包需要授权才能使用`viewer.display`功能。
该补助金由`capability_grant_manager`管理。

- **`allowed_packs`**：如果空数组`[]`，则允许来自所有包的请求
- **`max_token_lifetime`**：最大令牌过期时间（秒）

有关补助金如何运作的更多信息，请参阅[包开发指南第 6 节](../../pack-development.md)。

## 相关文档

- [Pack 开发指南](../../pack-development.md) — Pack 结构、生命周期和功能的详细信息
- [多语言包开发指南](../../multilang_pack_guide.md) — 如何用Python以外的语言开发包
