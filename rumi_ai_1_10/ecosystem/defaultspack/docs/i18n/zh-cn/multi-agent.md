<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](../ja/multi-agent.md) | [KR](../ko/multi-agent.md) | [CN](./multi-agent.md)
<!-- docs-i18n-links:end -->

# 公司工作区运行时

主要的公司协调路径是`CompanySlackRuntime`，实施于
`domain/company/message_router.py` 具有持久的运行时状态
§鲁米§0§。

运行时类似于 Slack：

- 通道和线程保存消息
- 向代理商提及路线工作
- 主动代理运行收到提及作为运行时指令
- 闲置代理通过`agent.delegate`接收委托的公司任务
- 运行链接将公司任务/线程/消息连接到 AgentEngine 运行
- 运营经理勾选检查开放、陈旧、阻塞和等待批准的工作
- 抄写员摘要涵盖公司、渠道、线程、任务和运行范围

公司层不执行工具。它创建、路由和观察
AgentEngine 运行策略、审批、模型功能、运行时配置文件和
工作区信任执行仍位于现有代理/工具的下游
运行时。

## 旧版兼容性

`/api/agent/multi/*` 仍然仅作为兼容性包装器可用。的
包装器发送到`CompanySlackRuntime`并返回`deprecation_warning`。

`domain/agent/multi.py` 仅限旧版。它不是默认的公司运行时。
