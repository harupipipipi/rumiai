<!-- docs-i18n-links:start -->
[EN](./compact_context_design.md) | [JP](./i18n/ja/compact_context_design.md) | [KR](./i18n/ko/compact_context_design.md) | [CN](./i18n/zh-cn/compact_context_design.md)
<!-- docs-i18n-links:end -->

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
