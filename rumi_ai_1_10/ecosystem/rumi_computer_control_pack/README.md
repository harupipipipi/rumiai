# Rumi Computer Control Pack

`rumi_computer_control_pack` is an optional declarative local-first pack for computer and desktop control workflows. It defines playbooks and safety contracts for macOS app workflows, screenshots, keyboard and mouse actions, foreground app context, terminal session observation, sandbox versus host boundaries, and evidence before state-changing actions.

## What It Provides

- Catalogs for host surfaces, control actions, evidence classes, and gateway-inspired local-first observations.
- Specs for session observation records and terminal/backend distinctions.
- Policies for evidence-first control and sandbox/host boundaries.
- Profiles for macOS desktop operation, local testing observation, and terminal session monitoring.
- Prompts and presets for careful use of screenshots, foreground app context, keyboard/mouse actions, and local testing.
- Examples for app navigation, screenshot-driven keyboard/mouse workflows, and terminal sandbox observation.
- Explicit overlap notes for `defaultspack`, `rumi_browser_automation_pack`, `rumi_security_review_pack`, and `rumi_agent_services_pack`.

## What It Does Not Provide

- No executable code, routes, handlers, flows, tools, or desktop drivers.
- No secrets, credentials, API keys, tokens, or remote endpoints.
- No network access by default; network is none by default.
- No override of the actual Computer Use plugin/tool, Chrome plugin, browser automation pack, or defaultspack grants.
- No automatic unrestricted control. The unrestricted local testing request is represented as a policy contract that still requires runtime/user approval.

## Design Evidence Reflected

- OpenClaw-style local-first gateway, desktop, voice, canvas, nodes, tools, and sandbox distinctions.
- Hermes-style terminal backend distinctions across local, Docker, SSH, Modal, Daytona, messaging, and CLI gateways.
- User demand for `@computer` and `@chrome` unrestricted local testing, captured here as an evidence-and-approval contract rather than new powers.

## Docs

Start with [docs/README.md](docs/README.md), then read [docs/interfaces.md](docs/interfaces.md) for boundaries and [docs/operations.md](docs/operations.md) for maintenance checks.
