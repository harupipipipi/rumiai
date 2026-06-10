<!-- docs-i18n-links:start -->
[EN](../../custom_node_pack_guide.md) | [JP](../ja/custom_node_pack_guide.md) | [KR](../ko/custom_node_pack_guide.md) | [CN](./custom_node_pack_guide.md)
<!-- docs-i18n-links:end -->

# 自定义节点包指南

能力图包可以在不更改核心运行时代码的情况下添加节点。

最小布局：

```text
my_pack/
  ecosystem.json
  capability_bindings.py
  nodes/search.node.json
  components/write_guard/node.json
  graphs/my_pack.graph.yaml
  profiles/my_pack.profile.yaml
```

对独立节点文档使用`nodes/*.node.json`。使用
`components/*/node.json` 当节点属于组件文件夹时。的
运行时仅加载已批准/哈希验证包的这些显式位置。

节点绑定应引用已注册的处理程序 ID，例如
§鲁米§0§。不要在节点中使用点分Python导入路径
文件。
