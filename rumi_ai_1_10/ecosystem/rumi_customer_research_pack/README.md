# Rumi Customer Research Pack

Declarative customer interview, survey, feedback evidence, consent/redaction, insight-card, and opportunity mapping pack.

This pack is local-first, declarative, and designed as a customization layer for Rumi. It adds domain-specific contracts, workflows, schemas, review gates, and handoff packets without adding executable runtime code.

## Provides

- participant_consent_record
- research_redaction_policy
- interview_evidence
- survey_synthesis
- feedback_to_insight_card
- opportunity_map
- evidence_linked_research_brief

## Does Not Provide

- live recruiting
- email or CRM writes
- generic web research
- product roadmap decisions
- analytics query execution
- contact enrichment
- message sending

## Consent And Redaction

Every participant and evidence record must carry consent_state, allowed_use, and redaction_state before synthesis. Revoked, unknown, raw_blocked, or do_not_use records produce blocked review packets and cannot contribute source_quote_ids to insight cards.

## Evidence-Linked Insight Cards

Insight cards must include supporting_evidence_ids and source_quote_ids that resolve to redacted, allowed source quotes. Cards remain drafts until handoff review names the next owner and preserves the evidence links.

## Required Secrets

None. The pack declares no credential requirement and no network access by default.

## Defaultspack Promotion

Not eligible by default. Promotion requires the blockers below to be cleared with maintainer-reviewed evidence:

- requires_participant_consent_model
- requires_redaction_review
- connector_delivery_owned_elsewhere
- does_not_recruit_or_write_crm
- must_validate_source_quote_coverage

## Handoff Model

The pack uses defaultspack as the base and hands adjacent runtime actions to explicit owner packs. If another pack overlaps, the narrower owner surface wins and this pack emits a reviewable handoff packet.
