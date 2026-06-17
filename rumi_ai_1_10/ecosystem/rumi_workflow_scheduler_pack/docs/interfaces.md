# Interfaces

## Flows, Functions, Handlers, Routes, Events, Stores

This pack declares no pack-owned flows, modifiers, functions, handlers, HTTP routes, runtime events, stores, timers, queues, workers, or executable tools.

## Catalogs And Specs

- `catalog/schedule_contracts.yaml`: contract types for cron-like schedules, intervals, one-shot wakeups, monitors, and follow-ups.
- `catalog/workflow_routes.yaml`: route metadata for app automation, defaultspack scheduler surfaces, agent services, connector gateways, and release packs.
- `catalog/delivery_handoffs.yaml`: delivery handoff contracts for messaging, chat, local notification, and artifact update targets.
- `catalog/scheduler_schema.json`: JSON schema for a local scheduler contract record.

## Policies

- `policies/retry_policy.yaml`: retry limits, backoff, idempotency, evidence requirements, stop conditions, and escalation defaults.

## Profiles

- `rumi_workflow_scheduler.scheduler_designer`: local-first profile for schedule design and review.

## Prompts

- `prompts/scheduler_designer.system.md`: design schedules with evidence, approvals, stop conditions, and owner routing.
- `prompts/schedule_review.system.md`: review existing schedule contracts for safety and overlap issues.

## Presets

- `presets/recurring_followup.preset.yaml`
- `presets/monitor_with_stop_conditions.preset.yaml`
- `presets/release_check_wakeup.preset.yaml`
- `presets/delivery_handoff_digest.preset.yaml`

## Examples

- `examples/daily_followup.example.yaml`
- `examples/monitor_with_retry.example.yaml`
- `examples/release_wakeup.example.yaml`

## Required Secrets

None.

This pack must not embed secrets, access tokens, API keys, OAuth material, bearer credentials, passwords, delivery endpoints, private keys, or remote account configuration.

## Network

No network access is required by this pack. Delivery and monitor targets are descriptive contracts only. Any real messaging, connector, or monitor execution must be performed by an approved owner pack or app automation surface with its own grants.

## Grants

Installing this pack should not grant scheduling, delivery, connector, browser, MCP, network, or release powers. It may recommend an owner route, but defaultspack, app automation tools, connector gateway packs, and release packs keep enforcement authority.

## Overlap Behavior

- With `defaultspack`: this pack defines scheduling contracts and route hints. It does not implement or override defaultspack scheduler, flow, agent, gateway, grant, or approval behavior.
- With `rumi_agent_services_pack`: this pack can describe recurring service cadence, monitor evidence, and follow-up handoffs. Agent services remain responsible for service orchestration.
- With `rumi_connector_gateway_pack`: this pack can describe delivery handoff intent and channel constraints. Connector gateway packs remain responsible for connector discovery, routing, and delivery execution.
- With `rumi_devops_release_pack`: this pack can describe release reminders, freeze-window checks, and signoff wakeups. Release packs keep release gates and deployment policy.

When overlap exists, prefer the owner pack for enforcement and use this pack only for local schedule contracts and review evidence.
