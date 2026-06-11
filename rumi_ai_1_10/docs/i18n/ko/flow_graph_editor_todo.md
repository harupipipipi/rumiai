<!-- docs-i18n-links:start -->
[EN](../../flow_graph_editor_todo.md) | [JP](../ja/flow_graph_editor_todo.md) | [KR](./flow_graph_editor_todo.md) | [CN](../zh-cn/flow_graph_editor_todo.md)
<!-- docs-i18n-links:end -->

# Flow Graph Editor TODO

이 TODO 는 `rumi_start` / port contracts / basepack bootstrap 의 도입 후에 남는 발전 과제를 정리한 것입니다.

## Next

- `rumi_graph`에서 실제 런타임용 `steps` 로의 컴파일 정밀도를 올린다
- `depends_on`와 graph branching의 대응 관계를 정리한다.
- port contracts를 Pack manifest에서 자동으로 공급할 수 있도록 한다.
- `basepack`를 bootstrap profile에서 독립 runtime pack으로 성장하거나 재검토
- graph editor UI snapshot / visual regression 테스트 추가

## 메모

- 지금 `basepack`은 안전을 위해 `defaultspack`을 target으로 한 bootstrap profile
- 지금의 execution은 뷰어 내 시뮬레이션으로 `rumi_start`에서 도달 가능한 step을 순서대로 흘린다
- 기존 런타임 호환성을 유지하기 위해 YAML에는 `steps`과 `rumi_graph`를 병기하고 있다
