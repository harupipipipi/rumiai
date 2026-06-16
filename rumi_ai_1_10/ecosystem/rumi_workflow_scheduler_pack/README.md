# Rumi Workflow Scheduler Pack

`rumi_workflow_scheduler_pack` is an optional, declarative, local-first pack for recurring workflows, monitors, wakeups, follow-ups, cron-like schedules, delivery handoffs, retry policy, evidence requirements, and stop conditions.

It reflects scheduler patterns seen in adjacent agent systems, such as cron schedulers, scheduled automations, messaging delivery, cron-like SDK automations, node-based gateways, and workflow wakeups, but expresses them as Rumi-native contracts. It does not run automations by itself.

## What It Provides

- Schedule contract specs for cron-like, interval, one-shot, monitor, wakeup, and follow-up workflows.
- Workflow routing metadata for app automation tools, defaultspack scheduler surfaces, agent service handoffs, connector gateways, and release workflows.
- Delivery handoff contracts for chat, messaging, webhook-like, and local notification surfaces.
- Retry, backoff, evidence, stop-condition, and escalation policy metadata.
- Profiles, prompts, presets, and examples for designing safe recurring workflows.

## What It Does Not Provide

- No executable scheduler, cron runner, queue worker, network connector, delivery client, or background daemon.
- No automatic installation of automations, no messaging delivery, and no monitor execution.
- No secrets, credentials, API keys, tokens, endpoints, or remote account configuration.
- No override of defaultspack grants, app automation approval, connector gateway policy, or release gates.

## Docs

Start with [docs/README.md](docs/README.md), then read [docs/architecture.md](docs/architecture.md), [docs/interfaces.md](docs/interfaces.md), and [docs/operations.md](docs/operations.md).
