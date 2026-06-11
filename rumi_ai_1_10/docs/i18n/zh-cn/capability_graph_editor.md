<!-- docs-i18n-links:start -->
[EN](../../capability_graph_editor.md) | [JP](../ja/capability_graph_editor.md) | [KR](../ko/capability_graph_editor.md) | [CN](./capability_graph_editor.md)
<!-- docs-i18n-links:end -->

# 能力图编辑器

该面板在`/api/panel/graphs`下公开图形编辑器API。

核心端点：

```text
GET  /api/panel/graphs
GET  /api/panel/graphs/{graph_id}
POST /api/panel/graphs
PUT  /api/panel/graphs/{graph_id}
POST /api/panel/graphs/{graph_id}/validate
POST /api/panel/graphs/{graph_id}/compile
POST /api/panel/graphs/edge-compatibility
GET  /api/panel/runtime-profile/current
```

验证并编译接受请求正文中的可选草案`graph`对象。
保存的图表写入`user_data/shared/graphs`。
