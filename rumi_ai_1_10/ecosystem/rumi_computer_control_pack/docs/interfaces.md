# Interfaces

## Flows, Functions, Handlers, Routes, Events, Stores

This pack declares no pack-owned flows, modifiers, functions, handlers, HTTP routes, runtime events, stores, or executable tools.

Referenced existing interfaces:

- `agent_chat` flow from `defaultspack`.
- Existing defaultspack approval, audit, grant, profile, and prompt interfaces.
- Existing concrete computer, browser, file, screenshot, and terminal tool families from `rumi_default_tools_pack` when installed and granted.

## Profiles

- `rumi_computer_control_pack.macos_desktop_operator`: desktop/app workflow profile.
- `rumi_computer_control_pack.local_testing_observer`: local unrestricted-testing contract profile with evidence requirements.
- `rumi_computer_control_pack.terminal_session_monitor`: terminal and backend observation profile.

## Prompts

- `desktop_control.system.md`: screenshot, foreground app, and keyboard/mouse discipline.
- `evidence_before_action.system.md`: evidence requirements before state-changing actions.
- `sandbox_host_boundary.system.md`: host, sandbox, terminal, and remote backend distinctions.

## Catalogs And Specs

- `catalog/control_surface_catalog.yaml`: action classes, evidence classes, surfaces, approvals, and overlap boundaries.
- `catalog/local_gateway_evidence.json`: OpenClaw/Hermes-inspired local gateway and terminal backend evidence.
- `specs/session_observation_spec.json`: schema-like observation record for desktop, browser, terminal, sandbox, and remote backend sessions.

## Policies

- `policies/evidence_first_control.policy.yaml`: what must be observed before clicking, typing, changing state, or escalating.
- `policies/sandbox_host_boundary.policy.yaml`: how to label host, local sandbox, container, SSH, Modal, Daytona, browser, and messaging contexts.

## Required Secrets

None.

## Network

Network is none by default. Live browser, Chrome, remote desktop, SSH, hosted preview, cloud sandbox, or remote terminal inspection requires explicit user request and runtime approval.

## Grants

This pack is not eligible for automatic all-ok grants. It documents how to reason about computer-control safety; it does not grant permissions or bypass `defaultspack` approval checks.

## Overlap Notes

- `defaultspack`: grants, approvals, auditing, and actual runtime routing remain defaultspack-owned.
- `rumi_browser_automation_pack`: browser navigation and DOM/browser QA playbooks remain browser-pack-owned; this pack owns host desktop context.
- `rumi_security_review_pack`: security pack reviews risk and grants; this pack records the operational evidence contract.
- `rumi_agent_services_pack`: service pack owns multi-agent coordination; this pack defines single-seat host-control handoff evidence.
