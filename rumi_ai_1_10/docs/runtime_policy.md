<!-- docs-i18n-links:start -->
[EN](./runtime_policy.md) | [JP](./i18n/ja/runtime_policy.md) | [KR](./i18n/ko/runtime_policy.md) | [CN](./i18n/zh-cn/runtime_policy.md)
<!-- docs-i18n-links:end -->

# Runtime Policy

Runtime policy is stored on Capability Profiles and copied into compiled runtime
profiles.

Supported fields:

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

`max_tool_calls` is enforced by AgentEngine. `allow_shell=false` and
`allow_file_write=false` filter provider tools and reject direct ToolExecutor
calls when tool metadata marks a shell or write action.

Node-level action filtering uses profile `node_settings`:

```json
{
  "node_settings": {
    "my_pack.search": {
      "allowed_actions": ["read_file", "search_code"]
    }
  }
}
```
