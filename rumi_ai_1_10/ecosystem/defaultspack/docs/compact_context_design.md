# Compact Context Design

Compact stores a small continuation packet:

- goal
- current task state
- decisions
- changed files
- tool and terminal results
- pinned context
- dropped context log
- blockers
- next steps

The compact packet is local data. A model may help summarize it, but the feature must also work with a deterministic fallback that extracts recent messages, plan state, and artifact metadata.
