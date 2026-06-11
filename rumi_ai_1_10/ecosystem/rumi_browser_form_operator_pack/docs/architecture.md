# Architecture

Rumi Browser Form Operator Pack is a declarative pack. It adds catalog, policy, profile, prompt, preset, and example assets; it does not install executable code.

## Boundaries
  - semantic_dom_collection: handoff_to_rumi_browser_element_pack
  - navigation_and_clicking: handoff_to_rumi_browser_automation_pack
  - pii_or_payment_risk: handoff_to_rumi_security_review_pack
  - post_submit_delivery: handoff_to_rumi_connector_gateway_pack
  - tool_aliases: prefer_explicit_pack_namespace

## Required Secrets
None.

## Evidence
The pack records workflow evidence before any handoff so defaultspack can keep a traceable decision chain.
