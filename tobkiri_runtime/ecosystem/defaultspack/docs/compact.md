# Compact

Compact keeps long-running work usable by replacing or supplementing verbose
history with small continuation packets and summaries. The compact packet is
local data and must preserve the information needed to resume work: goal,
current state, progress, decisions, constraints, changed files, tool and
terminal results, pinned context, dropped-context notes, memory flush refs, next
steps, and critical context.

## Modes

- Suggest: analyze history and return a plan of compactable segments. This is
  non-destructive by default.
- Apply: replace a selected message range with a summary message. This mutates
  chat history and should be explicit.
- Packet: write a compact packet under local defaultspack user data for durable
  resume and agent-runtime handoff.
- Restore: read a compact packet by safe id and rehydrate context.

## Non-Destructive Default

Automatic compact suggestion should default to plan-only behavior. It may use a
model to identify verbose or superseded segments, but failure falls back safely
to an empty plan. It should not delete messages, replace transcript ranges, or
drop source context unless the caller explicitly requests the apply path.

When compaction does apply, replacement messages must record metadata such as
summary status, edit type, original message count, original message ids, and
reason or instruction. This keeps the edit auditable and reversible at the
history layer.

## What To Preserve

Do not compact away:

- the original user goal;
- final results, decisions, approvals, or denials;
- recent active context;
- credentials or secrets in raw form;
- file paths, commands, errors, and validation results needed to continue;
- policy constraints such as workspace root confinement and local approval
  requirements.

## Security Invariants

- Compact is not an approval mechanism. A summary cannot grant permission for a
  tool call.
- Local policy, approval tokens, workspace confinement, and audit remain
  authoritative after compaction.
- P2P or external inputs may trigger a request for compaction only through
  normal message ingress; they cannot force destructive history edits.
- Compact packets are local artifacts. If a model helps summarize them, the
  deterministic fallback must still work without cloud access.
