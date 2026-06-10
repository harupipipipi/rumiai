<!-- docs-i18n-links:start -->
[EN](../../runtime_policy.md) | [JP](./runtime_policy.md) | [KR](../ko/runtime_policy.md) | [CN](../zh-cn/runtime_policy.md)
<!-- docs-i18n-links:end -->

# ランタイムポリシー

ランタイム ポリシーは機能プロファイルに保存され、コンパイルされたランタイムにコピーされます。
プロフィール。

サポートされているフィールド:

```json
{
  "policy": {
    "max_tool_calls": 5,
    "write_actions_require_approval": true,
    "allow_shell": false,
    "allow_file_write": false,
    "require_capability_graph_compile": true,
    "audit_level": "strict"
  }
}
```

`max_tool_calls` は AgentEngine によって強制されます。 `allow_shell=false`と
`allow_file_write=false` プロバイダー ツールをフィルターし、直接の ToolExecutor を拒否する
ツールのメタデータがシェルまたは書き込みアクションをマークするときに呼び出します。

ノードレベルのアクションフィルタリングはプロファイル`node_settings`を使用します。

```json
{
  "node_settings": {
    "my_pack.search": {
      "allowed_actions": ["read_file", "search_code"]
    }
  }
}
```
