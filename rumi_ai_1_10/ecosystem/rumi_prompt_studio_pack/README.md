# Rumi Prompt Studio Pack

Declarative prompt library, prompt linting, custom instruction migration, version ledger, and fixture dry-run contract pack.

## Provides

This pack owns prompt_artifact_catalog, prompt_lint_rubric, custom_instruction_migration, fixture_dry_run_contract, prompt_version_ledger. It gives Rumi a customizable, local-first contract for this domain without silently taking over adjacent runtime authority.

## Does Not Provide

This pack does not provide model benchmarking, model routing, persistent memory storage, tool creation, API creation, or code edits. Those surfaces are routed through setup-pack overlap policy and explicit handoff packets.

## Required Secrets

None.

## Network

None by default.

## Handoff Owners

- `rumi_model_evals_pack`
- `rumi_memory_knowledge_pack`
- `rumi_code_ide_pack`
- `rumi_knowledge_marketplace_pack`
