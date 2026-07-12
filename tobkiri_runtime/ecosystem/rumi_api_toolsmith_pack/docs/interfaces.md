# Interfaces

## Inputs
  - spec_url_or_path
  - operation_ids
  - mock_response_fixture
  - auth_boundary
  - schema_snapshot_or_sdl
  - operation_document
  - event_catalog
  - payload_examples

## Outputs
  - handoff_target_pack
  - acceptance_notes
  - evidence_summary
  - reviewer_decision
  - tool_schema_draft
  - operation_map
  - webhook_contract_summary
  - mock_test_evidence

## Handoff
All overlap with defaultspack-adjacent runtime work is routed by setup metadata rather than hidden behind aliases.

## Declarative Review Specs
OpenAPI review lives in `specs/openapi_schema_review.yaml`. GraphQL review lives in `specs/graphql_operation_review.yaml`. Webhook review lives in `specs/webhook_contract_review.yaml`. Mock evidence lives in `evidence/mock_test_evidence.schema.yaml`.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
