<!-- docs-i18n-links:start -->
[EN](../../../../examples/viewer_hello_pack/README.md) | [JP](../../../ja/examples/viewer_hello_pack/README.md) | [KR](../../../ko/examples/viewer_hello_pack/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 观众问候包

这是一个使用 Rumi AI OS 的 **viewer:display** 功能的示例包。
在 Rumi Viewer 中显示 Hello World 前端。

Pack还可以作为开发者可以复制和修改的模板。

---

## 目录结构

```
viewer_hello_pack/
├── ecosystem.json   # Pack マニフェスト
├── web/
│   ├── index.html   # フロントエンド（Hello World ページ）
│   └── app.js       # Kernel API 通信サンプル
└── README.md        # このファイル
```

---

## 什么是查看器：显示功能？

`viewer:display`是Rumi AI OS的核心能力之一，是Pack在Rumi Viewer（基于Tauri的桌面UI）中显示前端的权限。

具有此功能的包：

1. `web_mount`指定的目录中的静态文件从查看器分发。
2. 内核发出短期令牌，查看器使用该令牌进行身份验证
3. 前端可以调用内核API（`localhost:8765`）

能力的定义在`core_runtime/core_pack/core_viewer_capability/`中。

---

## 如何使用

### 1. 放置包

将此目录复制到`ecosystem/`：

```bash
cp -r docs/examples/viewer_hello_pack/ ecosystem/viewer_hello_pack/
```

### 2.启动内核

```bash
python -m rumi_ai
```

当内核启动时，它会自动扫描`ecosystem/viewer_hello_pack/ecosystem.json`。

### 3. 批准包

生态系统包首次需要批准（与 core_packs 不同，它们不会自动获得批准）。
请从内核 API 或管理屏幕批准该包。

### 4. 获得补助金

`viewer.display` 需要获得许可。
按如下方式配置授权：

- 将`viewer.display`授予`viewer_hello_pack`添加到内核GrantManager
- 一旦设置了授权，前端将通过查看器可见：显示功能

### 5. 用查看器显示

当您启动 Rumi Viewer 时，您将看到已批准/授予的包的前端。
`web/index.html` 在查看器中呈现，并且与内核 API 的通信演示正常工作。

---

## Ecosystem.json 解释

```json
{
  "pack_id": "viewer_hello_pack",
  "capabilities": ["viewer.display"],
  "web_mount": "web"
}
```

|领域|描述 |
|-----------|------|
| §鲁米§0§|请求的功能列表。指定`viewer.display` 启用查看器显示 |
| §鲁米§0§|提供静态文件的目录。相对于 Pack root 的路径 |

---

## 内核API通信

`web/app.js` 包含内核 API 的获取示例。

```javascript
fetch("http://localhost:8765/api/health", {
  method: "GET",
  headers: { "Accept": "application/json" }
})
  .then(response => response.json())
  .then(data => console.log(data));
```

内核 API 的默认端口是`8765`。

---

## 定制技巧

- **更改 UI**：编辑 `web/index.html` 的 HTML/CSS。还可以添加外部 CSS 框架
- **添加 API 调用**：向 `web/app.js` 添加新的获取调用
- **添加函数**：您还可以通过将函数添加到`ecosystem.json`的`functions`部分和`functions/`目录来实现后端处理
- **多页面**：将页面添加到`web/`目录并通过 SPA 路由和多个 HTML 文件支持它们
- **更改包名称**：请更改`ecosystem.json`的`pack_id`和`pack_identity`

---

## 相关文档

- [包开发指南](../../pack-development.md)
- [多语言包开发指南](../../multilang_pack_guide.md)
- [core_viewer_capability](../../../core_runtime/core_pack/core_viewer_capability/)
