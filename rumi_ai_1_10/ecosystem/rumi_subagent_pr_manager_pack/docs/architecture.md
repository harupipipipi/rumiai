# Architecture

Rumi Subagent PR Manager Pack is a declarative pack. It adds catalog, policy, profile, prompt, preset, and example assets; it does not install executable code.

## Boundaries
  - code_edits: handoff_to_rumi_code_ide_pack
  - agent_execution: handoff_to_rumi_agent_services_pack
  - merge_metrics: handoff_to_rumi_observability_pack
  - bundle_selection: handoff_to_rumi_pack_suite_pack
  - tool_aliases: prefer_explicit_pack_namespace

## Required Secrets
None.

## Evidence
The pack records workflow evidence before any handoff so defaultspack can keep a traceable decision chain.
