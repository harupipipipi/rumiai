# Agent Runtime Migration

No existing public agent or chat API was removed.

Compatibility behavior:

- old `defaults.agent.execute` returns the same envelope and execution payload
- old `defaults.agent.approve/reject/status/cancel` still use `execution_id`
- old in-memory engines continue to work while the process is alive
- missing in-memory engines are resolved from `AgentRunStore` when possible
- old memory calls continue through `MemoryStore` and mirror into Memory2

The runtime is feature-flag friendly through
`config/default_runtime_config.json` plus an optional
`user_data/shared/runtime_config.json` override, but this patch keeps the
durable store enabled by default because the legacy API shape is preserved.
