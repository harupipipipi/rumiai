# Rumi SOP Mining Pack

Declarative pack for turning local chat, tool, and audit traces into repeatable SOPs, checklists, runbooks, and human-approved workflow recipes.

## Owner Surfaces

- sop_pattern_catalog
- trace_record_schema
- redaction_policy
- human_approval_policy
- non_execution_boundary
- runbook_template
- review_checklist
- sop_mining_ledger
- workflow_recipe_catalog
- evidence_source_catalog

## Provides

This pack provides catalogs, schemas, policies, templates, profiles, prompts, presets, and examples for reviewers who want to mine repeatable process patterns from evidence that already exists locally. It is meant for turning "we keep doing this well" into a durable SOP with source trace references, redaction notes, approval gates, and review status.

## Does Not Provide

This pack does not execute automation, control browsers or computers, schedule jobs, create tools, invoke tools, send messages, or collect new live traces. Those surfaces remain with defaultspack or the specific owner pack named in setup metadata.

## Required Secrets

None. The pack is declarative and does not bundle credentials, API keys, tokens, cookies, passwords, or executable network clients.

## defaultspack Relationship

The pack depends on defaultspack for runtime context and setup discovery, but it does not replace defaultspack. It contributes review assets and boundary metadata for documenting SOPs from already available evidence.

## Evidence

Every mined SOP must point to redacted evidence references, capture the reviewer who approved promotion, and preserve a ledger entry explaining why the pattern is repeatable.

## Docs

Start with [docs/README.md](docs/README.md), then read [docs/interfaces.md](docs/interfaces.md) for the exact non-execution contract.
