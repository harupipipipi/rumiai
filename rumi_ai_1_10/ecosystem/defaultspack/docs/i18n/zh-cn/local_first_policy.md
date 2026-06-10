<!-- docs-i18n-links:start -->
[EN](../../local_first_policy.md) | [JP](../ja/local_first_policy.md) | [KR](../ko/local_first_policy.md) | [CN](./local_first_policy.md)
<!-- docs-i18n-links:end -->

# 本地优先策略

defaultspack 核心无需云 API 密钥即可使用。

该存储库的规范实现是
§鲁米§0§。旧的`ecosystem/defaults/`包
和单独的`harupipipipi/rumiai_defaults`存储库是兼容性或
快照源。新的运行时行为、安全规则、路由契约和 UI
默认值应首先在 defaultspack 中实现，并保留旧别名
仅在现有呼叫者仍然需要它们的情况下。

政策：

- 仅工作区文件，除非包明确授予更广泛的功能。
- 默认情况下网络被拒绝。
- 云模型提供者是可选的适配器。
- 文件写入、覆盖、删除、终端执行和 git 推送需要批准元数据。
- 秘密存储在 Rumi 秘密存储中，并且永远不会在 UI 目录中公开。
- 审计记录包含行动、风险、决策和经过编辑的论据。

核心可能包括本地文件、终端、git、本地模型提供者接口、内存、项目、紧凑、工件、安全、权限和审计。外部搜索、Reddit、浏览器网络、GitHub API、SaaS 集成和云计划仍然是可选的。

## 运行时默认值

- 有保证的启动模型是`stub/default`。
- 本地提供商，例如 Ollama、LM Studio、vLLM、llama.cpp 和本地提供商
  无需建立外部网络即可检测到 OpenAI 兼容端点
  请求。
- 云提供商是目录条目和配置目标，但它们是
  未选择作为新运行时默认值。
- 运行时中的自动云提供商注册被禁用，除非
  流程明确选择加入`RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS`。
- 本地提供商不需要 API 密钥。 API 密钥提示应仅出现
  选择云提供商或云模型后。

## 本地操作保护

敏感的本地操作受到独立于用户帐户的保护。这个
保护本地 HTTP 运行时免受跨站点或过时选项卡突变尝试的影响
无需添加登录、帐户创建、Supabase 或 Cloudflare 依赖项。

敏感突变包括文件写入/创建/删除/修补/恢复、终端
执行/流、git commit/push、集成秘密和浏览器
截图。他们必须在执行前通过这些检查：

- 客户端地址是环回的；
- Origin 标头（如果存在）是本地的；
- 具有来源的敏感突变包括`X-Rumi-CSRF`；
- 该块接收与该操作绑定的已签名的一次性批准令牌，并且
  参数哈希；
- 尝试、批准决定、执行、拒绝或失败被写入
  JSONL 审核日志，其中包含已编辑的机密。
