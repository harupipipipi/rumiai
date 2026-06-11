# Architecture

## Responsibility

`rumi_sop_mining_pack` is a declarative documentation pack. It converts evidence from local chat transcripts, tool traces, audit logs, test output, and handoff notes into repeatable SOPs. It does this by defining schemas, checklists, redaction rules, and human approval gates.

## Directory Layout

- `catalog/` contains allowed evidence sources, SOP pattern families, and workflow recipe lanes.
- `schemas/` contains JSON schemas for normalized trace records and mined SOP records.
- `policies/` contains redaction, human approval, and non-execution rules.
- `runbooks/` contains the SOP mining runbook template.
- `checklists/` contains the reviewer checklist.
- `ledgers/` contains the ledger schema for trace-to-SOP decisions.
- `profiles/`, `prompts/`, and `presets/` provide reviewer operating modes.
- `examples/` contains realistic, redacted examples that show the expected outputs.

## Runtime Contact

The pack has no components, no load order, no routes, and no executable code. Runtime setup discovers it through `ecosystem/setup_pack/rumi_sop_mining_pack/pack.json`; all runtime action surfaces stay with defaultspack or named owner packs.

## Boundary Design

The architecture is intentionally extraction-only:

- consume already available evidence references
- normalize and redact evidence
- identify repeatable process patterns
- draft SOPs, runbooks, checklists, and recipes
- require human approval before promotion

It never starts capture, runs automation, controls a browser or computer, schedules background work, creates tools, or invokes tools.
