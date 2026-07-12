# Operations

## Review Checklist
  - Confirm the user intent belongs to Rumi Runtime Benchmark Pack.
  - Check overlap policy before selecting tools.
  - Preserve evidence and validation commands.
  - Keep defaultspack promotion disabled until runtime evidence exists.
  - Preserve environment capture fields without secrets.
  - Preserve sampling plans with claim limits for smoke, comparison, and release-gate runs.
  - Keep reproducibility, sampling, latency/cost, and final integration review passes separate.

## Thickened Asset Checks
When changing benchmark behavior, verify reproducibility, sampling, latency/cost, and environment-capture assets together.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
