# SOP Mining Pack Docs

## Reading Order

1. [architecture.md](architecture.md) explains the pack responsibilities and file layout.
2. [interfaces.md](interfaces.md) defines accepted inputs, emitted artifacts, required secrets, network, grants, and handoff boundaries.
3. [operations.md](operations.md) describes the review workflow and contract test command.

## Core Assets

- `catalog/sop_pattern_catalog.yaml` lists repeatable patterns that can become SOPs.
- `catalog/trace_source_catalog.yaml` names supported local evidence types and required metadata.
- `catalog/workflow_recipe_catalog.yaml` maps mined SOPs into human-approved workflow recipe lanes.
- `schemas/trace_record.schema.json` defines normalized trace evidence records.
- `schemas/sop_record.schema.json` defines the reviewed SOP output record.
- `policies/redaction.policy.yaml` defines mandatory redaction and exclusion rules.
- `runbooks/sop_mining_runbook.template.yaml` provides the step-by-step mining template.
- `ledgers/sop_mining_ledger.schema.yaml` records review, redaction, and promotion decisions.

## Required Secrets

None. This pack only reads or references already available, locally reviewed evidence.
