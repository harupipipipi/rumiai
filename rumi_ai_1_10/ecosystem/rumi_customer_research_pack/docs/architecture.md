# Architecture

Rumi Customer Research Pack is a setup pack, not a runtime service. The architecture is intentionally simple:

1. Local input artifacts are normalized into schema-bound records.
2. Workflows produce drafts, review packets, and handoff packets.
3. Quality gates block unsafe or under-evidenced output.
4. Adjacent runtime actions are routed to owner packs through overlap policy.

This keeps Rumi customizable without making defaultspack absorb every specialized behavior.
