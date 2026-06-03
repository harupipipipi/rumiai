# Rumi Observability Pack

Rumi Observability Pack makes agent work inspectable: run ledgers, tool-call evidence, cost/latency summaries, failure taxonomy, and postmortems. It complements model evals, security, and devops packs without becoming a telemetry backend.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
