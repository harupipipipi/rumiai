<!-- docs-i18n-links:start -->
[EN](../../scheduler.md) | [JP](../ja/scheduler.md) | [KR](../ko/scheduler.md) | [CN](./scheduler.md)
<!-- docs-i18n-links:end -->

# 调度程序

`domain/scheduler` 将作业存储在 `user_data/shared/scheduler/jobs.json` 中并运行
`user_data/shared/scheduler/runs/{job_id}.jsonl`的历史。

支持的首次通过时间表是：

- `now`，`once`，`one_shot`
- `every 30m`，`every 1h`，`every 1d`
- 简单的五字段类似 cron 的分钟/小时形式

默认情况下，`no_agent` 作业处于禁用状态。它们仅在运行时配置设置时运行
`tool_policy.allow_shell=true` 和
`scheduler.allow_no_agent_scripts=true`，并且命令必须是 argv 列表
其可执行文件存在于`scheduler.no_agent_command_allowlist`中。的
跑步者从不使用`shell=True`。代理作业创建持久的代理执行
`cron:{job}` 会话密钥。
