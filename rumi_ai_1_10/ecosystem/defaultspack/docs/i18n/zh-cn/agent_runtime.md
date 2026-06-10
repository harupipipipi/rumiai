<!-- docs-i18n-links:start -->
[EN](../../agent_runtime.md) | [JP](../ja/agent_runtime.md) | [KR](../ko/agent_runtime.md) | [CN](./agent_runtime.md)
<!-- docs-i18n-links:end -->

# 持久代理运行时

defaultspack 现在在 `user_data/shared/agent_runtime/state.db` 中记录代理执行情况
并将活动转录事件镜像到下面的 JSONL 文件
§鲁米§0§。

现有的`defaults.agent.execute/status/approve/reject/cancel` API 仍然存在
兼容。 `blocks.agent._state` 仍然保留可用的实时引擎，但它
可以在进程本地化后从`AgentRunStore`重新创建`AgentEngine`外观
状态丢失，包括待批准的运行。

核心运行时添加仍然是通用的：文件锁、JSONL/SQLite 帮助程序、运行时
事件和审计编辑助手。代理域行为存在于
§鲁米§0§。
