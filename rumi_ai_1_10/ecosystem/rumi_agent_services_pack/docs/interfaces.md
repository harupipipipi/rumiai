# Interfaces

## Flows

This pack does not add executable flows or modifiers. It depends on defaultspack flow primitives and only declares workflow specs in `coordination/service_workflows.yaml`.

## Functions And Handlers

This pack does not add functions, handlers, Python entrypoints, or tool manifests.

## Routes

This pack does not add HTTP, WebSocket, desktop, CLI, or frontend routes.

## Events

The coordination specs define logical event names only:

- `service.intake.created`
- `service.plan.updated`
- `service.handoff.requested`
- `service.handoff.completed`
- `service.review.requested`
- `service.delivery.ready`

Runtimes may map these names to their own event bus. The pack does not register event handlers.

## Stores

This pack does not create stores. Consumers may persist task state through existing defaultspack memory, todo, transcript, artifact, or project stores.

## Required Secrets

None.

The pack must remain free of API keys, provider tokens, OAuth clients, bearer tokens, passwords, private URLs, and vendor credentials.

## Network

Network default: `deny`.

Profiles and presets may declare `browser_optional` or `web_optional`, but those values are descriptive. Runtime policy must still approve network-capable tools.

## Grants

No grants are required by this pack itself. If a runtime activates presets that use file, terminal, git, browser, web search, or subagent tools, the grants are provided by the underlying implementation packs and the runtime approval manager.

## Dependency Interfaces

Setup metadata declares dependencies on:

- `defaultspack >=2.0.0`
- `rumi_default_tools_pack >=1.0.0`
- `rumi_local_agent_pack >=1.0.0`

The pack overlaps with `rumi_local_agent_pack` in agent roles and presets, but it adds service-level routing and coordination rather than duplicate base profiles or executable tools.
