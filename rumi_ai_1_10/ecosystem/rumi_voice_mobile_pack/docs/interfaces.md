# Interfaces

## Inputs

- `goal`: The requested user outcome.
- `context`: Local files, connector handoffs, screenshots, logs, or prior artifacts as applicable.
- `constraints`: Safety, budget, privacy, schedule, or runtime boundaries.
- `handoff_target`: The pack or tool surface that should execute or receive the result.
- `transcript_ref`: Reference to a reviewed transcript when the input came from speech.
- `consent_refs`: Transcription, retention, notification, or action confirmation evidence.
- `intent_class`: Voice/mobile intent from `specs/intent_taxonomy.yaml`.

## Outputs

- `plan`: Domain-specific phased plan.
- `evidence`: References needed to prove completion.
- `handoff`: Explicit owner pack and next action.
- `status`: done, needs_review, blocked, or unsafe.
- `handoff_receipt`: Receipt schema reference for connector, scheduler, media, or device-action owners.

## Schemas And Policies

- Intent taxonomy: `specs/intent_taxonomy.yaml`
- Transcription and notification consent: `policies/transcription_notification_consent.policy.yaml`
- Mobile action safety: `checklists/mobile_action_safety_checklist.yaml`
- Handoff receipts: `specs/handoff_receipt.schema.yaml`
- Receipt template: `templates/mobile_handoff_receipt.template.yaml`

## Required Secrets

None.
