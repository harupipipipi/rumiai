<!-- docs-i18n-links:start -->
[EN](../../index.md) | [JP](../ja/index.md) | [KR](../ko/index.md) | [CN](./index.md)
<!-- docs-i18n-links:end -->

# defaultspack 文档索引

浏览 defaultspack 文档时从这里开始。规范的实现是
`rumi_ai_1_10/ecosystem/defaultspack/`。

本节中的术语是有意使用的：

- `rule`：范围内始终在线的指令层
- `skill`：基于触发器或按需指令和工作流程包
- `prompt`：在运行时组装的源资源或渲染模型文本
- `system prompt`：系统角色提示文本的低级 API/运行时术语
- `delegation`：将工作发送给另一个代理的规范操作
- `team workspace`：公司协调界面面向用户的名称；
  为了兼容性，内部 ID 和路由仍可能显示“`company`”

有关存储库范围内的术语表和迁移指南，请参阅
[`../../../docs/terminology.md`](../../../docs/terminology.md)。

## 方向

|主题 |文件|
|---|---|
| PR97 架构概述 | [defaultspack-explained.md](defaultspack-explained.md)|
|开始使用 | [getting-started.md](getting-started.md)|
|运行时架构| [architecture.md](architecture.md)|
|本地优先政策| [local_first_policy.md](local_first_policy.md)|
|安全与权限审核| [safety_permission_audit_design.md](safety_permission_audit_design.md)|

## 面向用户的系统

|主题 |文件|
|---|---|
|前端 shell 和路由 | [frontend.md](frontend.md)|
|前端扩展点 | [frontend_extensions.md](frontend_extensions.md)|
|用户界面和布局 | [ui_and_layout.md](ui_and_layout.md)|
|聊天模块| [chat.md](chat.md)|
|代理运行时 | [agent_runtime.md](agent_runtime.md)|
|团队工作区运行时 | [multi-agent.md](./multi-agent.md)|
|调度程序| [scheduler.md](scheduler.md)|

## 运行时原语

|主题 |文件|
|---|---|
|工具| [tool.md](tool.md)|
| MCP| [mcp.md](mcp.md)|
|流量引擎| [flow.md](flow.md)|
|提示和系统提示管道| [prompt.md](prompt.md)|
|内存| [memory.md](memory.md)|
|媒体| [media.md](media.md)|
|人工智能提供商| [ai-providers.md](ai-providers.md)|
|人工智能客户端| [ai_client.md](ai_client.md)|

## 集成与扩展

|主题 |文件|
|---|---|
|扩展defaultspack | [extending.md](extending.md)|
|输入配置文件| [input-profiles.md](input-profiles.md)|
|外部输入| [external-inputs.md](external-inputs.md)|
|网络钩子 | [webhooks.md](webhooks.md)|
|网关| [gateway.md](gateway.md)|
|交通 | [transport.md](transport.md)|
|能力依赖解析 | [capability/dependency-resolution.md](capability/dependency-resolution.md)|
