# Rumi Agent Services Pack

Rumi Agent Services Pack is an optional, declarative pack for multi-agent service workflows. It is inspired by the product shapes of ChatGPT Agent and Deep Research, Claude Code, Gemini CLI, Manus, Genspark, Cline, and OpenClaw/Hermes, but it remains local-first and vendor-neutral.

The pack provides profiles, prompts, presets, examples, a capability catalog, and coordination specs for service-style agents that plan, research, code, browse, review, and package deliverables. It does not provide model credentials, remote connectors, tool implementations, or runtime handlers.

## Provides

- Service profiles for directors, researchers, coding agents, browser operators, reviewers, and synthesizers.
- Prompt contracts for scoped work, evidence handling, handoffs, patch discipline, and delivery review.
- Presets that describe common agent service experiences without binding to one vendor.
- Declarative routing, handoff, workflow, and capability catalog specs.
- Local-first examples for research briefs, code changes, browser-assisted collection, and multi-agent reports.

## Does Not Provide

- No vendor API keys, endpoints, OAuth clients, or account credentials.
- No duplicate defaultspack flows, handlers, routes, stores, or tool executors.
- No new executable tools. It references capabilities from defaultspack, rumi_default_tools_pack, and rumi_local_agent_pack.
- No default network permission. Profiles default to local workspace and approval-gated tools.

## Documentation

Start with [docs/README.md](docs/README.md), then read [docs/architecture.md](docs/architecture.md), [docs/interfaces.md](docs/interfaces.md), and [docs/operations.md](docs/operations.md).
