# Subagent Team Workspace

The Subagent Team workspace is the user-facing name for the Slack/Discord-like
coordination surface. Defaultspack may still use `company` internally for
compatibility, but new UI, API, and docs should describe the surface as a team
of subagents working in channels.

## Architecture

- A team owns channels, threads, messages, tasks, inbox items, and run links.
- Channel messages are append-only coordination records; they do not execute
  tools directly.
- Mentions resolve to team agents. Idle agents receive delegated tasks through
  `agent.delegate`; active runs receive `run.instruction`.
- Public ids should be short, URL-safe, and human-scannable. Do not expose raw
  UUID strings in team, channel, message, task, inbox, or run-link ids.
- User-facing routes live under `/api/subagent-team/*`; existing
  `/api/company/*` and `/api/agent/companies/*` routes remain compatibility
  aliases.

## Creator

Creator prepares team assets before registration: proposed tools, agents,
channels, routing rules, and starter tasks. Preview mode is read-only. It may
validate and return generated definitions, but it must not register runtime
tools, persist files, create channels, enqueue tasks, or dispatch runs.

Only an explicit create/register action may make durable changes. Write-like
Creator actions still pass through the normal local approval, tool policy, and
audit paths.

## PM Gate

Client and president messages that target specialist agents pass through the
Project Manager when the PM gate is enabled. The PM receives the routed task,
the original requested agent ids, the source message, and the channel/thread
context. Specialists should not receive delegated runs until the PM decomposes
or approves the work.

The gate is a routing policy, not an approval bypass. Coding, terminal, file,
git, browser, external-send, and secret-bearing tools still rely on the normal
downstream policy checks.

## Rich Mode

Rich mode expands channel context with mentions, summaries, task state, run
links, and recent messages for high-context team rooms. It must also cap fanout
so a single message cannot dispatch an unbounded number of agent runs.

When rich fanout is capped, the runtime should route only the first allowed
targets, record the omitted target ids in metadata, and notify the PM or
operations manager so the remaining work can be triaged deliberately.

## Channel Checks

`channel.check` is the lightweight polling action for team agents and monitors.
It returns normalized context for one team channel: team id, channel id,
request trace, recent messages, dirty summaries, open tasks, active runs, and
unresolved mentions. A check is read-only and must not create messages, tasks,
or run dispatches by itself.
