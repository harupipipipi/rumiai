# Rumi Voice Mobile Pack

Rumi Voice Mobile Pack defines voice memo, speech command, mobile notification, and channel handoff workflows. It reflects Hermes/OpenClaw mobile and messaging ideas while avoiding transport implementation or credentials.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
