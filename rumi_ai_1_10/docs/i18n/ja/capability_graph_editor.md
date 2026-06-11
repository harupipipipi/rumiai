<!-- docs-i18n-links:start -->
[EN](../../capability_graph_editor.md) | [JP](./capability_graph_editor.md) | [KR](../ko/capability_graph_editor.md) | [CN](../zh-cn/capability_graph_editor.md)
<!-- docs-i18n-links:end -->

# 能力グラフエディター

このパネルでは、`/api/panel/graphs` の下にグラフ エディター API が公開されています。

コアエンドポイント:

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

リクエスト本文内のオプションのドラフト `graph` オブジェクトを検証してコンパイルします。
保存されたグラフは`user_data/shared/graphs`に書き込まれます。
