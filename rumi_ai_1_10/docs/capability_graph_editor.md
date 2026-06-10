<!-- docs-i18n-links:start -->
[EN](./capability_graph_editor.md) | [JP](./i18n/ja/capability_graph_editor.md) | [KR](./i18n/ko/capability_graph_editor.md) | [CN](./i18n/zh-cn/capability_graph_editor.md)
<!-- docs-i18n-links:end -->

# Capability Graph Editor

The panel exposes graph editor APIs under `/api/panel/graphs`.

Core endpoints:

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

Validate and compile accept an optional draft `graph` object in the request body.
Saved graphs are written to `user_data/shared/graphs`.
