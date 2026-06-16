# Interfaces

## Inputs
  - branch_name
  - pr_url
  - assigned_subagent_id
  - validation_commands

## Outputs
  - handoff_target_pack
  - acceptance_notes
  - evidence_summary
  - reviewer_decision

## Rich Assets
  - catalog/subagent_routing_matrix.yaml: maps PR lanes to owner, reviewer, and fallback subagents.
  - catalog/pr_acceptance_rubric.yaml: declares merge-readiness criteria and blocking failures.
  - templates/subagent_assignment_brief.template.yaml: standard assignment packet for one-pack-one-PR work.
  - ledgers/pr_evidence_ledger.schema.yaml: required evidence records for PR status and handoff traceability.
  - checklists/reviewer_handoff.checklist.yaml: maintainer-facing review checklist.

## Handoff
All overlap with defaultspack-adjacent runtime work is routed by setup metadata rather than hidden behind aliases.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
