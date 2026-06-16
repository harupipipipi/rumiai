# Rumi Document Intelligence Pack

Declarative PDF, contract, citation, redline, and document-question answering workflow pack.

This pack now includes claim-level citation mapping, page-span records, redline delta review, privacy classification, and repeated specialist review passes. It remains declarative: no runtime code, no secrets, and no network by default.

## Owner Surfaces
  - pdf_extraction
  - contract_clause_review
  - citation_traceability
  - redline_handoffs
  - page_span_mapping
  - privacy_review
  - multi_pass_specialist_review

## Thickened Review Assets
  - `catalog/citation_page_span_schema.json`
  - `catalog/redline_review_matrix.yaml`
  - `policies/citation_privacy_review.policy.yaml`
  - `coordination/subagent_review_roster.yaml`
  - `prompts/citation_redline_privacy_reviewer.system.md`

## Handoff Policy
This pack keeps its own scope narrow. When work crosses into code execution, connector delivery, browser operation, security, workspace artifacts, observability, or model scoring, it records the reason and hands off to the named pack in setup metadata.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
