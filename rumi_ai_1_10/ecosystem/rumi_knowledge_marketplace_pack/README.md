# Rumi Knowledge Marketplace Pack

Rumi Knowledge Marketplace Pack defines how Rumi should catalogue reusable skills, templates, playbooks, connector cards, and install candidates. It borrows from OpenClaw skills and Hermes skills, but treats marketplace content as untrusted until reviewed.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
