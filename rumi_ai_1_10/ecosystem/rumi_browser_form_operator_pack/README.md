# Rumi Browser Form Operator Pack

Declarative browser form recognition, field mapping, action replay, and submission safety pack.

## Owner Surfaces
  - semantic_form_fields
  - semantic_dom_dependency
  - safe_field_filling
  - field_risk_classification
  - submission_review
  - pre_submit_review
  - action_replay_receipts
  - submission_receipt_evidence

## Review Assets
  - `specs/form_taxonomy.yaml`: contact, account, checkout, legal, and public-send form taxonomy.
  - `specs/field_risk_classification.yaml`: low, medium, high, and irreversible field/action classification.
  - `specs/semantic_dom_dependency.yaml`: semantic DOM evidence required before field mapping.
  - `specs/submission_review_checklist.yaml`: pre-submit and post-submit review gates.
  - `evidence/submission_receipt_evidence.schema.yaml`: redacted receipt evidence for staged and submitted forms.

## Handoff Policy
This pack keeps its own scope narrow. When work crosses into code execution, connector delivery, browser operation, security, workspace artifacts, observability, or model scoring, it records the reason and hands off to the named pack in setup metadata.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
