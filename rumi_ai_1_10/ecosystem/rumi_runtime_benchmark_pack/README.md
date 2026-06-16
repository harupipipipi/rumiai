# Rumi Runtime Benchmark Pack

Declarative runtime benchmark, latency, cost, reproducibility, and tool-loop measurement pack.

This pack now includes reproducibility, latency/cost, sampling, and environment-capture material. It remains declarative: no runtime code, no secrets, and no network by default.

## Owner Surfaces
  - latency_measurement
  - cost_snapshot
  - tool_loop_reproducibility
  - runtime_comparison
  - sampling_plan
  - environment_capture
  - multi_pass_specialist_review

## Thickened Benchmark Assets
  - `catalog/environment_capture_schema.json`
  - `catalog/latency_cost_sampling_matrix.yaml`
  - `policies/environment_capture.policy.yaml`
  - `coordination/subagent_benchmark_review_roster.yaml`
  - `prompts/reproducible_latency_cost_reviewer.system.md`

## Handoff Policy
This pack keeps its own scope narrow. When work crosses into code execution, connector delivery, browser operation, security, workspace artifacts, observability, or model scoring, it records the reason and hands off to the named pack in setup metadata.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
