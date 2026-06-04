# Operations

Use `rumi_voice_mobile_pack` when the requested work fits its owner surfaces: voice_memo_contracts, mobile_notification_handoffs, speech_command_safety, on_the_go_briefings. Start by collecting enough evidence, then route any overlapping execution to the owner pack named in setup metadata. Do not treat a generated plan as completed work until the relevant evidence proves the requested outcome.

## Review Checklist

- Classify the voice/mobile intent before handoff.
- Require transcript evidence for speech-derived commands.
- Require consent for transcription, retention, notification delivery, repeated follow-up, and device actions.
- Block destructive, public, purchase, delete, or external-send voice commands until explicit confirmation and owner-pack review.
- Record a handoff receipt for every connector, scheduler, media, or computer-control handoff.
