# Rumi API Toolsmith Pack

Declarative API, OpenAPI, GraphQL, webhook, and tool-schema generation workflow pack.

## Owner Surfaces
  - openapi_tool_generation
  - openapi_schema_review
  - graphql_operation_mapping
  - graphql_variable_contracts
  - webhook_contracts
  - webhook_signature_policy_review
  - mock_server_tests
  - mock_test_evidence

## Review Assets
  - `specs/openapi_schema_review.yaml`: operation, parameter, body, response, and auth-boundary review.
  - `specs/graphql_operation_review.yaml`: query/mutation/subscription, variables, and partial-error review.
  - `specs/webhook_contract_review.yaml`: event, payload, signature-policy, replay, and mock-delivery review.
  - `evidence/mock_test_evidence.schema.yaml`: mocked test evidence schema for happy path, invalid input, redaction, and retry cases.

## Handoff Policy
This pack keeps its own scope narrow. When work crosses into code execution, connector delivery, browser operation, security, workspace artifacts, observability, or model scoring, it records the reason and hands off to the named pack in setup metadata.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
