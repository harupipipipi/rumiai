<!-- docs-i18n-links:start -->
[EN](../../defaultspack_authoring.md) | [JP](../ja/defaultspack_authoring.md) | [KR](../ko/defaultspack_authoring.md) | [CN](./defaultspack_authoring.md)
<!-- docs-i18n-links:end -->

# 默认包创作

Defaultspack 资源被编写为组件、块、函数、流、提示、节点和图形。

块位于`ecosystem/defaultspack/blocks/`下并暴露`run(input_data, context)`。功能体现在`functions/<function_id>/manifest.json`下；生成的包装器调用 defaultspack 函数调度程序。组件在`components/*/manifest.json`和`ecosystem.json`中通告可调用别名。

配置文件快照必须仅复制引用的流、提示、节点和块资源。他们使用源路径和 SHA-256 哈希编写`manifest.lock.json`，因此配置文件编辑和默认包更新仍然可以解释。
