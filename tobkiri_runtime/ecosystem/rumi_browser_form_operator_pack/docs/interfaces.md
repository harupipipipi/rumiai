# Interfaces

## Inputs
  - field_selector_map
  - visible_label_map
  - role_and_type_map
  - validation_message_map
  - field_risk_map
  - before_after_screenshot_ids
  - submit_intent
  - receipt_url

## Outputs
  - handoff_target_pack
  - acceptance_notes
  - evidence_summary
  - reviewer_decision
  - semantic_dom_dependency_report
  - pre_submit_review
  - submission_receipt
  - rollback_notes

## Handoff
All overlap with defaultspack-adjacent runtime work is routed by setup metadata rather than hidden behind aliases.

## Declarative Review Specs
Field-risk classification lives in `specs/field_risk_classification.yaml`. Semantic DOM dependency requirements live in `specs/semantic_dom_dependency.yaml`. Submission review gates live in `specs/submission_review_checklist.yaml`. Receipt evidence lives in `evidence/submission_receipt_evidence.schema.yaml`.
Form taxonomy lives in `specs/form_taxonomy.yaml`.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
