# Rumi Voice Mobile Pack

Rumi Voice Mobile Pack defines voice memo, speech command, mobile notification, and channel handoff workflows. It reflects Hermes/OpenClaw mobile and messaging ideas while avoiding transport implementation or credentials.

## Review Assets

- `specs/intent_taxonomy.yaml`: classifies voice memo, notification, scheduled briefing, device action, and sensitive audio intents.
- `policies/transcription_notification_consent.policy.yaml`: records consent requirements for transcription, retention, notifications, and follow-ups.
- `checklists/mobile_action_safety_checklist.yaml`: gates mobile/device actions before handoff.
- `specs/handoff_receipt.schema.yaml`: receipt schema for connector, scheduler, media, and computer-control handoffs.
- `templates/mobile_handoff_receipt.template.yaml`: template for reviewed voice/mobile handoff receipts.

## Required Secrets

None.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
