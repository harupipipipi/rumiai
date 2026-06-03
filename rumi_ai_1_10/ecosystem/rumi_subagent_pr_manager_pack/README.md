# Rumi Subagent PR Manager Pack

Declarative PM, subagent assignment, branch ledger, and one-pack-one-PR governance pack.

## Owner Surfaces
  - subagent_assignment
  - branch_pr_ledger
  - merge_readiness
  - pm_handoff
  - subagent_routing_matrix
  - pr_acceptance_rubric
  - evidence_ledger
  - handoff_checklist

## Quality Assets
This pack now includes a routing matrix, acceptance rubric, assignment brief template, evidence ledger schema, and handoff checklist. Those assets make repeated subagent use explicit: each PR lane names an accountable owner subagent, a reviewer subagent, and a fallback subagent, plus the evidence a human maintainer should expect before merge review.

## Handoff Policy
This pack keeps its own scope narrow. When work crosses into code execution, connector delivery, browser operation, security, workspace artifacts, observability, or model scoring, it records the reason and hands off to the named pack in setup metadata.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
