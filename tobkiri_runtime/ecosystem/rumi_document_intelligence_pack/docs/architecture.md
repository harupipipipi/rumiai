# Architecture

Rumi Document Intelligence Pack is a declarative pack. It adds catalog, policy, profile, prompt, preset, and example assets; it does not install executable code.

## Boundaries
  - slide_sheet_doc_creation: handoff_to_rumi_workspace_pack
  - web_research: handoff_to_rumi_research_pack
  - image_or_scan_analysis: handoff_to_rumi_multimodal_media_pack
  - sensitive_document_review: handoff_to_rumi_security_review_pack
  - tool_aliases: prefer_explicit_pack_namespace

## Required Secrets
None.

## Evidence
The pack records workflow evidence before any handoff so defaultspack can keep a traceable decision chain.
