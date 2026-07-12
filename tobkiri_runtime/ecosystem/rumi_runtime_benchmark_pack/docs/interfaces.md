# Interfaces

## Inputs
  - benchmark_seed
  - runtime_profile
  - sample_count
  - cost_latency_table

## Outputs
  - handoff_target_pack
  - acceptance_notes
  - evidence_summary
  - reviewer_decision

## Handoff
All overlap with defaultspack-adjacent runtime work is routed by setup metadata rather than hidden behind aliases.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## Thickened Benchmark Assets
  - `catalog/environment_capture_schema.json`: required and optional fields for reproducible runtime evidence.
  - `catalog/latency_cost_sampling_matrix.yaml`: latency, cost, reliability metrics and sample-count plans.
  - `policies/environment_capture.policy.yaml`: environment, cache, network, and cost-estimate discipline.
  - `coordination/subagent_benchmark_review_roster.yaml`: declarative repeated specialist passes for reproducibility, sampling, latency/cost, and final integration.
  - `prompts/reproducible_latency_cost_reviewer.system.md`: multi-pass benchmark review instructions.

These assets do not execute subagents. They define the review contract for repeated specialist passes while runtime approval and tool ownership remain in `defaultspack`.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
