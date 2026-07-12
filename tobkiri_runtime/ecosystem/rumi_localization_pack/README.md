# Rumi Localization Pack

Declarative terminology, protected-term, translation review, locale QA, tone preservation, and localization issue triage pack.

## Provides

This pack owns terminology_glossary, protected_terms_policy, locale_qa_matrix, translation_review_checklist, tone_preservation, translation_issue_triage, segment_evidence_map, and localization_handoff_packet. It gives Rumi a customizable, local-first contract for this domain without silently taking over adjacent runtime authority.

It is intended for app strings, docs copy, support macros, release notes, policy copy, and connector message drafts when the user has supplied local source evidence. Review outputs must preserve source and target segment IDs so another owner can perform extraction, layout implementation, export, or delivery.

## Does Not Provide

This pack does not provide document parsing, document mutation, frontend design, browser automation, workspace export generation, connector publishing, connector delivery, generic QA, model evals, or live translation runtime. Those surfaces are routed through setup-pack overlap policy and explicit handoff packets.

## Required Secrets

None.

## Network

None by default.

## Handoff Owners

- `rumi_document_intelligence_pack`
- `rumi_frontend_design_pack`
- `rumi_workspace_pack`
- `rumi_connector_gateway_pack`
- `rumi_agentic_qa_pack`
- `rumi_model_evals_pack`
