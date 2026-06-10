<!-- docs-i18n-links:start -->
[EN](./custom_node_pack_guide.md) | [JP](./i18n/ja/custom_node_pack_guide.md) | [KR](./i18n/ko/custom_node_pack_guide.md) | [CN](./i18n/zh-cn/custom_node_pack_guide.md)
<!-- docs-i18n-links:end -->

# Custom Node Pack Guide

Capability Graph packs can add nodes without changing core runtime code.

Minimum layout:

```text
my_pack/
  ecosystem.json
  capability_bindings.py
  nodes/search.node.json
  components/write_guard/node.json
  graphs/my_pack.graph.yaml
  profiles/my_pack.profile.yaml
```

Use `nodes/*.node.json` for standalone node documents. Use
`components/*/node.json` when the node belongs to a component folder. The
runtime only loads these explicit locations for approved/hash-verified packs.

Node bindings should reference registered handler ids such as
`my_pack:search.compile_node`. Do not use dotted Python import paths in node
files.
