# Architecture

Rumi API Toolsmith Pack is a declarative pack. It adds catalog, policy, profile, prompt, preset, and example assets; it does not install executable code.

## Boundaries
  - mcp_server_registration: handoff_to_rumi_mcp_gateway_pack
  - external_connector_delivery: handoff_to_rumi_connector_gateway_pack
  - auth_or_secret_review: handoff_to_rumi_security_review_pack
  - mock_execution: handoff_to_rumi_sandbox_runtime_pack
  - tool_aliases: prefer_explicit_pack_namespace

## Required Secrets
None.

## Evidence
The pack records workflow evidence before any handoff so defaultspack can keep a traceable decision chain.
