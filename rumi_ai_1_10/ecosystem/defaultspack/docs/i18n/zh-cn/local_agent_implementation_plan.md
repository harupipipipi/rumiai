<!-- docs-i18n-links:start -->
[EN](../../local_agent_implementation_plan.md) | [JP](../ja/local_agent_implementation_plan.md) | [KR](../ko/local_agent_implementation_plan.md) | [CN](./local_agent_implementation_plan.md)
<!-- docs-i18n-links:end -->

# 本地代理实施计划

## P0

- 能力目录：加载`capabilities/*.capability.yaml`并公开`/api/capabilities`。
- 本地代理配置文件：加载`profiles/local_agent.profile.yaml`并将其公开在`/api/agent-service/manifest`中。
- 计划和步骤：使用`schemas/agent_plan.schema.yaml`、`schemas/agent_step.schema.yaml`和`blocks.agent.plan`。
- 文件工作区：将所有操作保留在工作区根目录内；公开读取、写入、创建、删除、列表、搜索、差异、快照、恢复。
- 终端和 git：对风险进行分类，需要批准字段才能执行，并审核尝试的操作。
- 安全：默认网络拒绝、编辑机密并记录审核元数据。

## P1

- 内存和项目上下文：具有查看和删除操作的本地 JSON/文件存储。
- 紧凑：滚动摘要、固定上下文和恢复笔记。
- 工件：使用元数据创建本地 markdown/text/code/json/yaml/html/csv 工件。

## P2

- 研究：首先是本地资源，然后是可选的网络/浏览器提供商。
- UI：计划、工具调用、文件树、差异、终端、工件、内存和批准面板。

## 测试

- 验证目录文件加载。
- 验证回退 HTTP 注册表中是否存在路由。
- 验证配置文件和功能策略元数据。
- 验证工作空间安全性并批准风险操作的元数据。
