# Architecture

`rumi_observability_pack` separates intent, evidence, policy, and handoff.

1. The event schema records local agent, model, tool, cost/latency, incident, and handoff events with explicit privacy and redaction state.
2. The run ledger contract groups events into a reviewable account of a run, including owner packs, cost units, latency units, evidence references, and unresolved followups.
3. Privacy and cost policies keep raw prompts, connector payloads, private URLs, account identifiers, and billed-cost claims out of shared artifacts unless separately justified.
4. Incident checklists and postmortem templates turn failures into reviewable local evidence packets before routing remediation elsewhere.
5. Setup metadata exposes dependencies, overlaps, marketplace status, signing status, and defaultspack promotion blockers.

The architecture keeps Rumi modular: each pack owns one domain and routes overlapping work to the pack that owns that surface.

`rumi_observability_pack` does not create a telemetry backend, does not execute tools, and does not override the Computer Use, browser, model eval, security, devops, or agent-service packs. Its runtime role is declarative: describe the evidence contract, make handoffs inspectable, and keep records safe enough for local review.
