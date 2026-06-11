<!-- docs-i18n-links:start -->
[EN](../../runtime_policy.md) | [JP](../ja/runtime_policy.md) | [KR](../ko/runtime_policy.md) | [CN](./runtime_policy.md)
<!-- docs-i18n-links:end -->

# 运行时策略

运行时策略存储在功能配置文件中并复制到编译的运行时中
配置文件。

支持的字段：

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

`max_tool_calls` 由 AgentEngine 强制执行。 `allow_shell=false`和
`allow_file_write=false`过滤提供者工具并拒绝直接ToolExecutor
当工具元数据标记 shell 或写入操作时调用。

节点级操作过滤使用配置文件`node_settings`：

```json
{
  "node_settings": {
    "my_pack.search": {
      "allowed_actions": ["read_file", "search_code"]
    }
  }
}
```
