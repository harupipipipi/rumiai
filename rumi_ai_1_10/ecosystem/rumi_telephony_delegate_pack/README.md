# Rumi Telephony Delegate Pack

Declarative provider-neutral call task, dial approval, consent script, transcript redaction, escalation, and never-call policy pack.

This pack is local-first, declarative, and designed as a customization layer for Rumi. It adds domain-specific contracts, workflows, schemas, review gates, and handoff packets without adding executable runtime code.

## Provides

- call_task_contract
- pre_call_script
- dial_approval_gate
- consent_disclosure_script
- call_session_state
- takeover_escalation
- transcript_redaction_contract
- never_call_list
- mock_dial_readiness

## Does Not Provide

- actual dialing
- ASR/TTS runtime
- contact lookup
- calendar mutation
- payment or purchase execution
- external connector writes
- emergency services

## Safety Invariants

- Real dialing is never performed by this pack; provider-ready output is a handoff packet only.
- Human approval must be explicit, evidence-linked, and scoped to a single number alias plus script ID.
- Active never-call entries block the task before any provider handoff is produced.
- Disallowed intent, declined consent, emergency handling, and payment or purchase requests abort into review.
- Opening disclosure and consent question text are required before any mock dial readiness claim.
- Transcript handoffs must replace configured PII classes before downstream review.
- Takeover escalations must name a human or owner pack and record whether abort is required.

## Required Secrets

None. The pack declares no credential requirement and no network access by default.

## Defaultspack Promotion

Not eligible by default. Promotion requires the blockers below to be cleared with maintainer-reviewed evidence:

- no_actual_dialing_runtime
- requires_external_real_world_action_approval_class
- requires_never_call_policy
- requires_redactable_transcript_storage
- must_pass_disallowed_intent_abort_cases

## Handoff Model

The pack uses defaultspack as the base and hands adjacent runtime actions to explicit owner packs. If another pack overlaps, the narrower owner surface wins and this pack emits a reviewable handoff packet.
