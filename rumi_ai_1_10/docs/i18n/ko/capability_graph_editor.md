<!-- docs-i18n-links:start -->
[EN](../../capability_graph_editor.md) | [JP](../ja/capability_graph_editor.md) | [KR](./capability_graph_editor.md) | [CN](../zh-cn/capability_graph_editor.md)
<!-- docs-i18n-links:end -->

# 공정 능력 그래프 편집기

패널은 `/api/panel/graphs` 아래에 그래프 편집기 API를 표시합니다.

핵심 엔드포인트:

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

요청 본문에서 선택적 초안 `graph` 개체를 확인하고 컴파일하여 수락합니다.
저장된 그래프는 `user_data/shared/graphs`에 기록됩니다.
