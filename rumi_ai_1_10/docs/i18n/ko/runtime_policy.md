<!-- docs-i18n-links:start -->
[EN](../../runtime_policy.md) | [JP](../ja/runtime_policy.md) | [KR](./runtime_policy.md) | [CN](../zh-cn/runtime_policy.md)
<!-- docs-i18n-links:end -->

# 런타임 정책

런타임 정책은 기능 프로필에 저장되고 컴파일된 런타임에 복사됩니다.
프로필.

지원되는 분야:

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

`max_tool_calls`은 AgentEngine에 의해 시행됩니다. `allow_shell=false` 및
`allow_file_write=false` 필터 제공자 도구 및 직접 ToolExecutor 거부
도구 메타데이터가 셸 또는 쓰기 작업을 표시할 때 호출됩니다.

노드 수준 작업 필터링은 `node_settings` 프로필을 사용합니다.

```json
{
  "node_settings": {
    "my_pack.search": {
      "allowed_actions": ["read_file", "search_code"]
    }
  }
}
```
