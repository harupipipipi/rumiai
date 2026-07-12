# Operations

## Review Checklist
  - Confirm the user intent belongs to Rumi API Toolsmith Pack.
  - Check overlap policy before selecting tools.
  - Preserve evidence and validation commands.
  - Keep defaultspack promotion disabled until runtime evidence exists.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.

## Thick Review Checklist
  - OpenAPI operations have stable operation ids, request/response shape review, auth-boundary notes, and mock evidence.
  - GraphQL operations classify query/mutation/subscription risk, variables, nullability, partial errors, and sensitive variables.
  - Webhook contracts record event version, signature header names without secrets, replay policy, duplicate delivery, malformed payload, and retry cases.
  - Mock-test evidence includes happy path, invalid input, redaction, error-shape, and side-effect boundary assertions.
