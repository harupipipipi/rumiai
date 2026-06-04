# Interfaces

## Inputs

- Local artifacts supplied by the user or by an adjacent owner pack.
- Schema-bound records listed in `ecosystem.json`.
- Evidence IDs, source spans, and explicit uncertainty notes.
- Phone target aliases only; raw phone numbers belong in an external owner system.

## Outputs

- Evidence-linked drafts.
- Review checklist results.
- Handoff packets with owner pack, reason, and artifact path.
- Blocked packets for never-call matches, missing approval, declined consent, disallowed intent, or takeover-required states.

## Call Handoff Contract

- Handoff packets are not calls and must not be represented as completed dialing.
- A provider handoff requires approved number alias, approved script ID, consent disclosure review, never-call evidence, and explicit human approval.
- Transcript handoffs require reviewed redaction records for configured PII classes.

## Handoff Owners

- `rumi_voice_mobile_pack`: Owns mobile voice capture, ASR/TTS, and user-device voice surfaces.
- `rumi_multimodal_media_pack`: Owns media transcript processing and audio artifacts.
- `rumi_connector_gateway_pack`: Owns contact lookup and provider connectors.
- `rumi_meeting_intelligence_pack`: Owns meeting recap and action extraction after a transcript exists.
- `rumi_security_review_pack`: Reviews real-world action risk, fraud, and policy edge cases.
- `rumi_business_ops_pack`: Owns downstream business workflow execution after human approval.

## Required Secrets

None.

## Does Not Provide

- actual dialing
- ASR/TTS runtime
- contact lookup
- calendar mutation
- payment or purchase execution
- external connector writes
- emergency services
