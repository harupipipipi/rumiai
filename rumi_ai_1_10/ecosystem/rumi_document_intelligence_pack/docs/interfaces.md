# Interfaces

## Inputs
  - page_span
  - quote_digest
  - risk_label
  - handoff_artifact_id

## Outputs
  - handoff_target_pack
  - acceptance_notes
  - evidence_summary
  - reviewer_decision

## Handoff
All overlap with defaultspack-adjacent runtime work is routed by setup metadata rather than hidden behind aliases.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## Thickened Review Assets
  - `catalog/citation_page_span_schema.json`: claim-to-citation records, page-span rules, and evidence confidence labels.
  - `catalog/redline_review_matrix.yaml`: redline change classes, risk flags, and handoff outputs.
  - `policies/citation_privacy_review.policy.yaml`: privacy classifications and checks before summary, redline handoff, or external sharing.
  - `coordination/subagent_review_roster.yaml`: declarative repeated specialist passes for citation mapping, redline review, privacy review, and final evidence integration.
  - `prompts/citation_redline_privacy_reviewer.system.md`: multi-pass review instructions.

These assets do not execute subagents. They define the review contract for repeated specialist passes while runtime approval and tool ownership remain in `defaultspack`.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
