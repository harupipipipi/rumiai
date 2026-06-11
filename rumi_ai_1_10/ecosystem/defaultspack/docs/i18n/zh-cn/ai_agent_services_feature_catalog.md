<!-- docs-i18n-links:start -->
[EN](../../ai_agent_services_feature_catalog.md) | [JP](../ja/ai_agent_services_feature_catalog.md) | [KR](../ko/ai_agent_services_feature_catalog.md) | [CN](./ai_agent_services_feature_catalog.md)
<!-- docs-i18n-links:end -->

# AI代理服务功能目录

作为defaultspack的标准词汇，现代基于AI代理的服务的功能是按本地优先级组织的。

|编号 |类别 |灵感来源 |本地|应用程序编程接口 |优先|状态 |默认包目标 |
|---|---|---|---:|---:|---|---|---|
|计划模式 |代理核心 |抄本、克劳德代码、马努斯 |是的 |没有| P0|已实施 | `schemas/agent_plan.schema.yaml`，`prompts/planner.system.md`|
|步骤执行 |代理核心 |法典，马努斯 |是的 |没有| P0|已实施 | `schemas/agent_step.schema.yaml`，`blocks/agent/*`|
|审批工作流程 |安全|法典，克劳德·代码 |是的 |没有| P0|已实施 | `schemas/tool_call.schema.yaml`，`capabilities/safety.capability.yaml`|
|本地文件工作空间 |工作区 |法典，克劳德代码，光标 |是的 |没有| P0|已实施 | `capabilities/local_file.capability.yaml`，`blocks/coding/*`|
|终端外壳 |终端|法典，克劳德·代码 |是的 |没有| P0|已实施 | `capabilities/terminal.capability.yaml`|
| git_集成 | git | git法典，克劳德代码，光标 |是的 |部分 | P0|已实施 | `capabilities/git.capability.yaml`|
|记忆 |个性化| ChatGPT，克劳德项目 |是的 |没有| P1 |已实施 | `capabilities/memory.capability.yaml`|
|项目工作空间 |项目| ChatGPT 项目，光标 |是的 |没有| P1 |已实施 | `schemas/project.schema.yaml`|
|紧凑上下文 |背景 |克劳德代码，ChatGPT |是的 |没有| P1 |已实施 | `capabilities/compact.capability.yaml`|
|文物|文物|克劳德、ChatGPT、Genspark |是的 |没有| P1 |已实施 | `schemas/artifact.schema.yaml`|
|本地研究 |研究|马努斯 Genspark |部分 |没有| P2 |已实施 | `schemas/research_result.schema.yaml`|
|浏览器可选 |可选浏览器 |马努斯，张开爪|部分 |可选 | P3 |计划| `capabilities/browser_optional.capability.yaml`|
|本地模型提供者 |型号| OpenClaw、Ollama 应用程序 |是的 |没有| P0|已实施 | `capabilities/local_model.capability.yaml`|

规则：

- 核心功能必须在没有云 API 密钥的情况下工作。
- 网络和外部 SaaS 提供商是可选适配器。
- 文件写入、删除、终端和 git 推送需要策略门。
- UI 从目录 API 接收功能和组件契约，而不是硬编码的假设。
