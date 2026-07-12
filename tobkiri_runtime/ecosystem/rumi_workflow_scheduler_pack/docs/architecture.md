# Architecture

## Responsibility

`rumi_workflow_scheduler_pack` describes how recurring and scheduled workflows should be represented in Rumi. It covers cron-like schedules, intervals, one-shot wakeups, recurring follow-ups, monitors, delivery handoffs, retry policy, evidence requirements, stop conditions, and escalation notes.

## Evidence Reflected

The pack is Rumi-native but reflects common scheduler patterns observed in agent ecosystems:

- cron schedulers and scheduled automations, including delivery to messaging platforms.
- SDK-level cron automation concepts.
- node and gateway based scheduled workflow designs.

These patterns are represented as local contracts only. The pack does not copy or implement external runtimes.

## Non-Responsibility

The pack does not implement cron execution, queues, timers, monitors, message delivery, webhooks, network calls, routes, handlers, stores, or executable tools. Scheduling execution belongs to defaultspack, the app automation tool, connector gateway packs, or other owner packs when available.

## Directory Layout

- `ecosystem.json`: pack identity, vocabulary, local-only metadata, and asset index.
- `catalog/schedule_contracts.yaml`: schedule kinds, required fields, clock posture, and approval posture.
- `catalog/workflow_routes.yaml`: route metadata for app automation, defaultspack, agent services, connector gateway, and release workflows.
- `catalog/delivery_handoffs.yaml`: delivery handoff contracts and channel safety posture.
- `catalog/scheduler_schema.json`: JSON schema for local scheduler contract records.
- `policies/retry_policy.yaml`: retry, backoff, idempotency, evidence, and stop-condition policy.
- `profiles/`: scheduler designer profile metadata.
- `prompts/`: system prompts for designing and reviewing schedules.
- `presets/`: named recurring workflow patterns.
- `examples/`: example local schedule records.
- `docs/`: pack-specific documentation required by the documentation contract.

## Execution Path

1. A user selects the pack through setup-pack metadata.
2. A Rumi surface reads the profile, preset, catalog, policy, and prompt assets.
3. The user or agent drafts a schedule contract with evidence and stop conditions.
4. If execution is requested, the request is routed to an approved owner such as the app automation tool or defaultspack scheduler surface.
5. Delivery, retries, and monitors remain inert unless the owner runtime accepts and approves them.

## Runtime Contact Points

- Routes to the app automation tool when an app-level automation API is available.
- Routes to defaultspack scheduler, flow, agent, and gateway capabilities when those exist and are approved.
- Complements `rumi_agent_services_pack` by defining recurring service cadence and handoff contracts.
- Complements `rumi_connector_gateway_pack` by describing delivery handoffs without performing connector delivery.
- Complements `rumi_devops_release_pack` by describing release check reminders and signoff schedules without bypassing release gates.

No pack-owned Python modules are imported during normal use.
