# Rumi Frontend Design Pack

Rumi Frontend Design Pack covers UI planning, design-system fit, frontend implementation briefs, responsive QA, screenshot review, and app-building handoffs. It is inspired by modern web-app builders and coding agents, but stays Rumi-native: code edits belong to code packs and visual evidence belongs to media/browser packs.

## Quality Assets

- `catalog/design_system_fit_rubric.yaml` scores whether a proposed UI matches the existing product density, component idioms, accessibility posture, and visual language.
- `catalog/responsive_qa_matrix.yaml` defines mobile/tablet/desktop viewport checks, screenshot evidence, and owner handoffs for browser execution.
- `schemas/component_acceptance.schema.yaml` and `checklists/component_acceptance.checklist.yaml` define acceptance criteria for component briefs, states, copy, layout, and handoff evidence.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
