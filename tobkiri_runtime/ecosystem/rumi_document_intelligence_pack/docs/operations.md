# Operations

## Review Checklist
  - Confirm the user intent belongs to Rumi Document Intelligence Pack.
  - Check overlap policy before selecting tools.
  - Preserve evidence and validation commands.
  - Keep defaultspack promotion disabled until runtime evidence exists.
  - Preserve claim-level citation records with page spans or missing-evidence states.
  - Preserve redline delta risk flags and privacy classification before handoff.
  - Keep citation, redline, privacy, and final evidence-integration review passes separate.

## Thickened Asset Checks
When changing document-intelligence behavior, verify citation, page-span, redline, privacy, and repeated specialist review assets together.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
