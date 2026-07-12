# Interfaces

## Inputs
  - scenario_id
  - expected_observation
  - actual_observation
  - triage_owner_pack

## Outputs
  - handoff_target_pack
  - acceptance_notes
  - evidence_summary
  - reviewer_decision

## Rich Assets
  - catalog/qa_routing_matrix.yaml: maps QA lanes to scenario, adversarial, regression, evidence, and handoff subagents.
  - catalog/acceptance_rubric.yaml: declares agentic QA readiness criteria and blocking failures.
  - catalog/scenario_catalog.yaml: stores reusable scenario definitions with observations and owner packs.
  - ledgers/qa_evidence_ledger.schema.yaml: required evidence records for scenario replay and triage.
  - checklists/qa_replay.checklist.yaml: replay checklist for repeatable acceptance reviews.
  - templates/regression_triage_report.template.yaml: report template for failures and owner handoffs.

## Handoff
All overlap with defaultspack-adjacent runtime work is routed by setup metadata rather than hidden behind aliases.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
