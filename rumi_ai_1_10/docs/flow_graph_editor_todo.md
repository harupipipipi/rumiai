<!-- docs-i18n-links:start -->
[EN](./flow_graph_editor_todo.md) | [JP](./i18n/ja/flow_graph_editor_todo.md) | [KR](./i18n/ko/flow_graph_editor_todo.md) | [CN](./i18n/zh-cn/flow_graph_editor_todo.md)
<!-- docs-i18n-links:end -->

# Flow Graph Editor TODO

This TODO organizes the development issues that remain after the introduction of `rumi_start` / port contracts / basepack bootstrap.

## Next

- Improve compilation accuracy from `rumi_graph` to `steps` for real runtime
- Organize the correspondence between `depends_on` and graph branching
- Allow port contracts to be automatically provided from Pack manifest
- Reconsider whether to grow `basepack` from bootstrap profile to independent runtime pack.
- Add UI snapshot/visual regression tests for graph editor

## Notes

- The current `basepack` is a bootstrap profile that targets `defaultspack` for safety.
- The current execution is a simulation in the viewer, which sequentially flows the reachable steps from `rumi_start`
- To maintain compatibility with existing runtimes, `steps` and `rumi_graph` are included in YAML.
