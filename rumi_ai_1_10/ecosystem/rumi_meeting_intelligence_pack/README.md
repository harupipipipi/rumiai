# Rumi Meeting Intelligence Pack

Declarative local-first meeting preparation, decision capture, action extraction, and follow-up handoff pack.

## Provides

This pack owns meeting_prebrief, decision_log, action_item_extraction, evidence_linked_recap, followup_draft_contract. It gives Rumi a customizable, local-first contract for this domain without silently taking over adjacent runtime authority.

## Does Not Provide

This pack does not provide live capture, connector sending, calendar mutation, business workflow execution, or document parsing. Those surfaces are routed through setup-pack overlap policy and explicit handoff packets.

## Required Secrets

None.

## Network

None by default.

## Handoff Owners

- `rumi_connector_gateway_pack`
- `rumi_workflow_scheduler_pack`
- `rumi_voice_mobile_pack`
- `rumi_document_intelligence_pack`
- `rumi_business_ops_pack`
