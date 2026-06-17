# Interfaces

## Flows, Functions, Handlers, Routes, Events, Stores

This pack declares no pack-owned flows, modifiers, functions, handlers, HTTP routes, events, or stores.

Referenced existing interfaces:

- `agent_chat` flow from `defaultspack`.
- `defaultspack.coding_workspace` graph for local repository evidence gathering.
- File, git, terminal, browser companion, and web research tool families from `rumi_default_tools_pack`, subject to runtime approval.

## Profiles

- `rumi_devops_release_pack.ci_triage`: local-first CI failure and log triage.
- `rumi_devops_release_pack.release_manager`: release evidence, notes, and gate review.
- `rumi_devops_release_pack.rollback_planner`: rollback and post-incident recovery planning.

## Prompts

- `ci_triage.system.md`: CI/log failure triage with evidence and next-check discipline.
- `release_evidence.system.md`: release notes, gates, deploy runbook, and verification evidence.
- `rollback_runbook.system.md`: rollback decision, safety checks, and recovery communication.

## Catalogs

- `catalog/release_gate_catalog.yaml`: release gates, evidence classes, runbook sections, rollback phases, and Cloudflare Workers notes.
- `catalog/devops_operations_catalog.json`: machine-readable operation categories, ownership boundaries, and network posture.

## Presets

- GitHub Actions triage.
- Cloudflare Workers release review.
- Local-first release gate.
- Incident rollback.

## Required Secrets

None.

## Network

Network access is none by default. If a user asks to inspect live CI, GitHub Actions, Cloudflare, or deployment state, the agent must use approved connectors or user-provided local exports and follow runtime approval policy.

## Grants

The setup pack is not eligible for automatic all-ok grants. It adds operating guidance only and depends on existing grants for defaultspack and default tools.

## Dependencies

- Required: `defaultspack >=2.0.0`.
- Required: `rumi_default_tools_pack >=1.0.0`.
- Complementary: `rumi_code_ide_pack`.
- Complementary: `rumi_agent_services_pack`.

## Overlap Notes

- With `defaultspack`: this pack uses core graph, profile, prompt, approval, and audit primitives. It is not a promotion target for defaultspack.
- With `rumi_default_tools_pack`: this pack references tools for local evidence gathering. It does not ship tools.
- With `rumi_code_ide_pack`: code pack owns source edits; this pack owns operational gates, release evidence, runbooks, and rollback planning.
- With `rumi_agent_services_pack`: services pack owns service composition; this pack owns release and incident evidence around services.
