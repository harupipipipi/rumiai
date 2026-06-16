# Architecture

## Responsibility

`rumi_computer_control_pack` owns declarative computer-control playbooks and contracts:

- macOS foreground app workflows.
- Screenshot and visual-state evidence.
- Keyboard and mouse action planning.
- Foreground app and window context.
- Terminal session observation.
- Sandbox versus host boundary classification.
- Evidence required before state-changing actions.

## Boundaries

This pack does not own actual execution. It does not replace the Computer Use plugin/tool, Chrome plugin, browser automation runtime, defaultspack grants, or default tool implementations.

Adjacent ownership:

- `defaultspack` owns grants, approvals, auditing, profile loading, and runtime routing.
- `rumi_default_tools_pack` owns concrete computer, browser, file, and terminal tool implementations.
- `rumi_browser_automation_pack` owns browser navigation and browser QA playbooks.
- `rumi_security_review_pack` owns review of permission, privacy, and grant risk.
- `rumi_agent_services_pack` owns service-agent coordination and handoff topology.

## Directory Layout

- `ecosystem.json`: pack identity, dependencies, asset index, and no-code/no-network posture.
- `catalog/`: host-control surfaces and design evidence catalogs.
- `specs/`: observation record schema for sessions and terminal/backend distinctions.
- `policies/`: evidence-first and sandbox/host boundary policies.
- `profiles/`: desktop, local testing, and terminal observation profiles.
- `prompts/`: behavior contracts for computer-control sessions.
- `presets/`: named playbook bundles.
- `examples/`: example local-first workflows.
- `metadata/`: overlap and defaultspack promotion metadata.
- `docs/`: pack-specific documentation.

## Execution Path

1. The setup-pack selector discovers `ecosystem/setup_pack/rumi_computer_control_pack/pack.json`.
2. The runtime discovers declarative assets listed in `ecosystem.json`.
3. A selected profile references existing defaultspack flow and tool routing conventions.
4. Policies and prompts guide evidence gathering before any state-changing computer action.
5. Actual tool execution remains governed by installed tools, grants, and approvals.

## Design Evidence

The pack records two inspection themes:

- OpenClaw: local-first gateway, desktop/voice/canvas/nodes/tools surfaces, and sandbox distinctions.
- Hermes: terminal backends including local, Docker, SSH, Modal, Daytona, plus messaging and CLI gateways.

These references shape the vocabulary and boundary policy; they do not add vendor-specific code.
