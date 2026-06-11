<!-- docs-i18n-links:start -->
[EN](../../subagents.md) | [JP](../ja/subagents.md) | [KR](../ko/subagents.md) | [CN](./subagents.md)
<!-- docs-i18n-links:end -->

# 委托兼容性

鲁米不再将“子代理”视为主要的架构概念。

对于面向用户的措辞，首选：

- `team workspace` 适用于长期运行的多代理工作区表面
- `team` 表示该工作空间内的合作代理组
- `delegation` 用于将有界工作发送给另一个代理
- `specialist` 或 `delegated agent` 适用于范围狭窄的工人角色

`company` 和 `subagent` 保留旧 API 的兼容性/内部名称，
路由、存储的标识符或文档仍然使用它们。

规范的运行时合约是：

- `chat.message`：正常对话输入
- `run.instruction`：排队转向或运行时指导
- `run.interrupt`：紧急运行时指导
- `agent.delegate`：一次委托工具运行
- `model.call`：默认情况下没有工具的一个有界模型到模型问题
- `model.switch`：持久对话模型更改
- `model.route`：回合范围的路由覆盖

`subagent` 仍然作为旧版本的兼容性名称和面向用户的别名
仍然涉及委派工作的路线、功能、工具、标签和文档。

## 当前边界

- `agent.delegate` = 一次委托运行，可以使用工具、批准和正常运行时策略
- `multi-agent` = 协调多个委派员工的团队执行
- `tool_selector`、`prompt_compactor`、`context_summarizer`、`model_router`和`vision_ocr`等实用程序角色是通过`model.call`风格的实用程序路由而不是特殊的子代理框架来实现的

## 兼容路径

这些兼容表面仍然可用：

- `/api/agent/subagent`
- `defaults.agent.run_subagent`
- `defaultspack.agent.run_subagent`
- `defaults.tool.subagent`
- `defaultspack.tool.subagent`
- `rumi_default_tools_pack`中的`subagent`儿童对话工具

保留它们是为了向后兼容，并且应该通过共享输入进行路由，
模型、工具和策略契约，而不是引入并行行为。

实际上这意味着：

- 实用程序角色兼容性调用通过共享`model.call`式实用程序路由进行路由
- 类似任务的兼容性调用通过公共输入调度程序路由，如`agent.delegate`

旧文档中所说的 `company workspace`，请阅读为今天的 `team workspace`
除非文本专门描述兼容性 API 或存储的运行时
标识符。

## 政策和批准

使用兼容性`subagent`别名不会绕过：

- 工具政策
- 审批门
- 运行时配置文件工具连接
- 模型能力检查
- 工作空间信任要求

如果委派的工作需要工具，则应使用与任何其他工作相同的策略和审批路径
其他运行。
