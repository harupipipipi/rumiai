# Compaction

`domain/context_engine` provides token estimation, stable prompt layers,
overflow detection, compact packets, and replacement history helpers.

Compact packets include goal, current state, progress, decisions, constraints,
changed files, tool results, pinned context, dropped context logs, memory flush
refs, next steps, critical context, source transcript, and replacement
transcript identifiers.

Replacement history preserves system messages and keeps recent tool call/result
pairs together. Missing tool results receive a compact stub; orphan tool results
are dropped.
