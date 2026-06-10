<!-- docs-i18n-links:start -->
[EN](../../migration_agent_runtime.md) | [JP](../ja/migration_agent_runtime.md) | [KR](../ko/migration_agent_runtime.md) | [CN](./migration_agent_runtime.md)
<!-- docs-i18n-links:end -->

# 代理运行时迁移

没有删除现有的公共代理或聊天 API。

兼容性行为：

- 旧的`defaults.agent.execute`返回相同的信封和执行负载
- 旧的`defaults.agent.approve/reject/status/cancel`仍使用`execution_id`
- 旧的内存引擎在进程处于活动状态时继续工作
- 缺失的内存引擎在可能的情况下通过`AgentRunStore`解决
- 旧的内存调用继续通过`MemoryStore`并镜像到内存2

运行时是功能标志友好的
`config/default_runtime_config.json` 加上一个可选的
`user_data/shared/runtime_config.json` 覆盖，但此补丁保留
默认情况下启用持久存储，因为保留了旧版 API 形状。
