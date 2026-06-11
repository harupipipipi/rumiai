<!-- docs-i18n-links:start -->
[EN](../../flow_graph_editor_todo.md) | [JP](../ja/flow_graph_editor_todo.md) | [KR](../ko/flow_graph_editor_todo.md) | [CN](./flow_graph_editor_todo.md)
<!-- docs-i18n-links:end -->

# 流程图编辑器 TODO

此 TODO 整理了引入`rumi_start`/端口合约/基础包引导程序后仍然存在的开发问题。

## 下一步

- 将真实运行时的编译精度从`rumi_graph`提高到`steps`
- 组织`depends_on`和图分支之间的对应关系
- 允许从 Pack 清单自动提供端口合同
- 重新考虑是否将`basepack`从引导程序配置文件发展为独立运行时包。
- 为图形编辑器添加 UI 快照/视觉回归测试

## 注释

- 当前的`basepack`是一个引导配置文件，以`defaultspack`为目标，以确保安全。
- 当前执行是查看器中的模拟，它按顺序从`rumi_start`开始执行可到达的步骤
- 为了保持与现有运行时的兼容性，YAML 中包含`steps` 和`rumi_graph`。
