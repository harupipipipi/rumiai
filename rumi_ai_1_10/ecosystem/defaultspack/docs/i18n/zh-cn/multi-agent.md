<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](../ja/multi-agent.md) | [KR](../ko/multi-agent.md) | [CN](./multi-agent.md)
<!-- docs-i18n-links:end -->

# 团队工作区运行时

面向用户的主要协调路径是团队工作区运行时。
在内部，实施仍然以`CompanySlackRuntime`为中心，
在`domain/company/message_router.py`中实现，具有持久的运行时状态
`domain/company/runtime_store.py`。

运行时类似于 Slack：

- 通道和线程保存消息
- 向代理商提及路线工作
- 主动代理运行收到提及作为运行时指令
- 闲置代理通过`agent.delegate`接收委派的团队任务
- 运行链接将公司兼容性记录和团队线程/消息连接到
  AgentEngine 运行
- 运营经理勾选检查打开、陈旧、阻止和等待批准
  工作
- 抄写员摘要涵盖工作区、通道、线程、任务和运行范围

公司层不执行工具。它创建、路由和观察
AgentEngine 运行策略、审批、模型功能、运行时配置文件和
工作区信任执行仍位于现有代理/工具的下游
运行时。

## 术语注释

- `delegation` 是将工作发送给另一个代理的规范操作名称。
  在运行时术语中，这映射到`agent.delegate`。
- `subagent` 应被解读为委托的兼容性或遗留标签
  工作，而不是作为单独的主要运行时架构。
- `company` 在代码路径、id 和旧路由中仍然很常见。文档使用
`team workspace` 描述面向用户的表面时。

## 旧版兼容性

`/api/agent/multi/*` 仍然仅作为兼容性包装器可用。的
包装器发送到`CompanySlackRuntime`并返回`deprecation_warning`。

`domain/agent/multi.py` 仅限旧版。这不是默认的团队工作空间
运行时。
