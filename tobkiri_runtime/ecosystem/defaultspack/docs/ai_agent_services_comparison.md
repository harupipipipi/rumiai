# AI Agent Services Comparison

| Service | Local files | Terminal | Git | Plan | Approval | Memory | Projects | Artifacts | Research | Browser |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Codex | yes | yes | yes | yes | yes | session | repo | patch | optional | optional |
| Claude Code | yes | yes | yes | yes | yes | project | yes | files | optional | optional |
| ChatGPT Projects | partial | no | no | partial | n/a | yes | yes | yes | yes | no |
| Manus | yes | yes | partial | yes | yes | task | task | yes | yes | yes |
| Genspark | partial | partial | no | yes | partial | task | task | report | yes | yes |
| OpenClaw | yes | yes | yes | yes | yes | local | local | files | optional | optional |
| defaultspack target | yes | yes | yes | yes | yes | local | local | local | local-first | optional |

defaultspack adopts the local and extensible parts first. Cloud model APIs, web search, GitHub API, Reddit, and browser network access remain optional providers.

## OpenClaw Verification Notes

Verified on 2026-06-03 against the published `openclaw` npm package and
official repository metadata:

- `npm view openclaw version dist-tags.latest bin engines --json` reported
  `2026.5.28`, `openclaw.mjs`, and `node >=22.19.0`.
- `npm pack openclaw@latest` succeeded and exposed bundled docs for
  personal assistant setup, workspace bootstrapping, heartbeat behavior,
  sub-agents, tool policy, and Claw Supervisor.
- Non-interactive CLI probes such as `openclaw status --all --json` and
  `openclaw health --json` were attempted through `npx`; in this Windows
  workspace they did not complete before the local timeout, so the comparison
  relies on package metadata plus inspected bundled docs rather than a running
  gateway.

OpenClaw strengths worth tracking in defaultspack:

- Always-on assistant framing with explicit heartbeat configuration and
  workspace-scoped `HEARTBEAT.md`.
- Sub-agent runs with queueing, max concurrency, stale-run handling, recovery
  notes, and explicit completion delivery semantics.
- Operational commands for status, health, doctor, gateway, and dashboard.
- Supervisor design for attachable Codex app-server sessions, transcript
  reads, steering, interruption, spawn, handoff, and MCP callbacks.

defaultspack 24h soak now records matching durability signals:

- Durable runner start metadata, heartbeat timestamps, and health status.
- Leased active task claims so crash/restart resume can detect stale work.
- Queue consumption when a task result is recorded.
- Competitor comparison findings in the final soak report.
- Manual soak workflow fails early when required live-provider credentials are
  absent instead of burning the full 24h window with guaranteed failures.
