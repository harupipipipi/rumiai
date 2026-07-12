# Architecture

Rumi Agentic QA Pack is a declarative pack. It adds catalog, policy, profile, prompt, preset, and example assets; it does not install executable code.

## Boundaries
  - model_scoring: handoff_to_rumi_model_evals_pack
  - browser_e2e_steps: handoff_to_rumi_browser_automation_pack
  - unsafe_behavior: handoff_to_rumi_security_review_pack
  - run_ledger: handoff_to_rumi_observability_pack
  - tool_aliases: prefer_explicit_pack_namespace

## Required Secrets
None.

## Evidence
The pack records workflow evidence before any handoff so defaultspack can keep a traceable decision chain.
