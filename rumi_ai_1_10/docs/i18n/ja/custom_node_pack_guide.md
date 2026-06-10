<!-- docs-i18n-links:start -->
[EN](../../custom_node_pack_guide.md) | [JP](./custom_node_pack_guide.md) | [KR](../ko/custom_node_pack_guide.md) | [CN](../zh-cn/custom_node_pack_guide.md)
<!-- docs-i18n-links:end -->

# カスタム ノード パック ガイド

ケイパビリティ グラフ パックでは、コア ランタイム コードを変更せずにノードを追加できます。

最小レイアウト:

```text
my_pack/
  ecosystem.json
  capability_bindings.py
  nodes/search.node.json
  components/write_guard/node.json
  graphs/my_pack.graph.yaml
  profiles/my_pack.profile.yaml
```

スタンドアロン ノード ドキュメントには `nodes/*.node.json` を使用します。使用する
`components/*/node.json` ノードがコンポーネント フォルダーに属している場合。の
ランタイムは、承認/ハッシュ検証されたパックのこれらの明示的な場所のみを読み込みます。

ノード バインディングは、次のような登録されたハンドラー ID を参照する必要があります。
`my_pack:search.compile_node`。ノードで点線の Python インポート パスを使用しないでください
ファイル。
