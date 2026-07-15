# Interfaces

## Inputs

- Local artifacts supplied by the user or by an adjacent owner pack.
- Schema-bound records listed in `ecosystem.json`.
- Evidence IDs, source spans, source_quote_ids, consent_state, allowed_use, and explicit uncertainty notes.

## Outputs

- Evidence-linked drafts with supporting_evidence_ids and source_quote_ids.
- Review checklist results that include consent/redaction decisions.
- Handoff packets with owner pack, reason, artifact path, and evidence links.

## Handoff Owners

- `rumi_connector_gateway_pack`: Recruiting, calendar, and source system retrieval are connector-owned.
- `rumi_business_ops_pack`: CRM writes, outbound email, and business workflow execution remain outside this pack.
- `rumi_research_pack`: General web research and market scans remain research-owned.
- `rumi_data_analysis_pack`: Large survey statistics and analytics queries are data-analysis-owned.
- `rumi_meeting_intelligence_pack`: Raw call or meeting transcript normalization is meeting-intelligence-owned.

## Required Secrets

None.

## Does Not Provide

- live recruiting
- email or CRM writes
- generic web research
- product roadmap decisions
- analytics query execution
- contact enrichment
- message sending
