<!-- docs-i18n-links:start -->
[EN](./multi-agent.md) | [JP](./i18n/ja/multi-agent.md) | [KR](./i18n/ko/multi-agent.md) | [CN](./i18n/zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# Company Workspace Runtime

The primary company coordination path is `CompanySlackRuntime`, implemented in
`domain/company/message_router.py` with durable runtime state in
`domain/company/runtime_store.py`.

The runtime is Slack-like:

- channels and threads hold messages
- mentions route work to agents
- active agent runs receive mentions as runtime instructions
- idle agents receive delegated company tasks through `agent.delegate`
- run links connect company tasks/threads/messages to AgentEngine runs
- operations manager ticks inspect open, stale, blocked, and approval-waiting work
- scribe summaries cover company, channel, thread, task, and run scopes

The company layer does not execute tools. It creates, routes, and observes
AgentEngine runs so policy, approval, model capability, runtime profile, and
workspace trust enforcement remain downstream in the existing agent/tool
runtime.

## Legacy Compatibility

`/api/agent/multi/*` remains available only as a compatibility wrapper. The
wrappers post into `CompanySlackRuntime` and return a `deprecation_warning`.

`domain/agent/multi.py` is legacy-only. It is not the default company runtime.
