# Durable Agent Runtime

defaultspack now records agent executions in `user_data/shared/agent_runtime/state.db`
and mirrors active transcript events to JSONL files under
`user_data/shared/agent_runtime/transcripts/`.

The existing `defaults.agent.execute/status/approve/reject/cancel` API remains
compatible. `blocks.agent._state` still keeps live engines when available, but it
can recreate an `AgentEngine` facade from `AgentRunStore` after process-local
state is lost, including pending approval runs.

Core runtime additions remain generic: file locks, JSONL/SQLite helpers, runtime
events, and audit redaction helpers. Agent domain behavior lives in
`domain/agent_runtime`.
