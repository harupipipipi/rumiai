# Rumi Business Ops Pack

Rumi Business Ops Pack organizes AI-agent service work for sales follow-ups, support triage, marketing briefs, procurement comparisons, CRM hygiene, and admin operations. It mirrors the practical reach of Genspark/Manus/OpenClaw style agents while keeping connector execution, scheduling, and workspace artifacts in their owning packs.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
