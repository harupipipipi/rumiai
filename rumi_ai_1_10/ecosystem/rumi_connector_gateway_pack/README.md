# Rumi Connector Gateway Pack

Rumi Connector Gateway Pack defines how Rumi should reason about external connectors and messaging channels without bundling credentials or transport code. It is inspired by OpenClaw and Hermes gateway patterns, but keeps Rumi's local-first grant model: installed connector tools execute; this pack owns namespace policy, scope cards, inbound-risk review, and handoff contracts.

## Required Secrets

None.

## Overlap Policy

- `defaultspack` owns approvals, grants, provider keys, and active pack selection.
- Installed connector plugins own Slack, Gmail, Google Drive, GitHub, Notion, and similar transport execution.
- `rumi_mcp_gateway_pack` owns MCP server namespace and unsupported MCP classification.
- `rumi_workflow_scheduler_pack` owns recurring schedule contracts and wakeups.
- This pack owns connector scope review cards, channel handoff envelopes, and inbound prompt-risk classification.
