# Rumi Sandbox Runtime Pack

Rumi Sandbox Runtime Pack defines contracts for local, container, SSH, remote, and ephemeral execution environments. It draws on Hermes terminal backends and agent sandbox patterns, but remains declarative: actual execution stays with approved tools and defaultspack grants.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
