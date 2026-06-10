<!-- docs-i18n-links:start -->
[EN](../../subagents.md) | [JP](../ja/subagents.md) | [KR](../ko/subagents.md) | [CN](./subagents.md)
<!-- docs-i18n-links:end -->

# 委托兼容性

鲁米不再将“子代理”视为主要的架构概念。

规范的运行时合约是：

- `chat.message`：正常对话输入
- `run.instruction`：排队转向或运行时指导
- `run.interrupt`：紧急运行时指导
- `agent.delegate`：一次委托工具运行
- `model.call`：默认情况下没有工具的一个有界模型到模型问题
- `model.switch`：持久对话模型更改
- `model.route`：回合范围的路由覆盖

`subagent` 仍然作为旧路由的兼容性名称和面向用户的别名，
仍然涉及委派工作的功能、工具、标签和文档。

## 当前边界

- `agent.delegate` = 一次委托运行，可以使用工具、批准和正常运行时策略
- `multi-agent` = 协调多个委派员工的团队执行
- `tool_selector`、`prompt_compactor`、`context_summarizer`、`model_router`和`vision_ocr`等实用程序角色是通过`model.call`风格的实用程序路由而不是特殊的子代理框架来实现的

## 兼容路径

这些兼容表面仍然可用：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- `rumi_default_tools_pack`中的`subagent`儿童对话工具

保留它们是为了向后兼容，并且应该通过共享输入进行路由，
模型、工具和策略契约，而不是引入并行行为。

实际上这意味着：

- 实用程序角色兼容性调用通过共享`model.call`风格的实用程序路由进行路由
- 类似任务的兼容性调用通过通用输入调度程序路由，如`agent.delegate`

## 政策和批准

使用兼容性`subagent`别名不会绕过：

- 工具政策
- 审批门
- 运行时配置文件工具连接
- 模型能力检查
- 工作空间信任要求

如果委派的工作需要工具，则应使用与任何其他工作相同的策略和审批路径
其他运行。
