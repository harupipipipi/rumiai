# Rumi Meeting Intelligence Pack

The Rumi Meeting Intelligence Pack is a local-first setup pack for preparing meetings, turning existing transcripts into decisions, extracting action items, drafting follow-ups, and packaging evidence-linked recaps.

It is intentionally declarative. It does not fetch remote data, join calls, record audio, parse documents, schedule work, send messages, or update business systems. It consumes transcripts, notes, agenda text, and already extracted files that the user or another owner pack has made available.

## Required Secrets

None.

## Local-First Contract

- Network access is none by default.
- Inputs must be existing local files, pasted text, or user-provided transcript exports.
- Every decision, action, and recap claim must link to an evidence reference.
- Follow-up output is draft-only until a human reviewer or another owner pack executes it.
- Privacy-sensitive attendee data is summarized and redacted unless the user explicitly asks to keep it.

## Owned Surfaces

- Meeting prep briefs from already available agenda, notes, and local context.
- Transcript-to-decisions extraction with source spans and confidence.
- Action extraction with owner, deadline, dependency, and unresolved-state fields.
- Follow-up drafts for email, chat, or generic handoff, without sending.
- Evidence-linked recap bundles that include a ledger and handoff queue.

## Handoff Surfaces

- Connectors and remote fetch: `rumi_connector_gateway_pack`.
- Scheduling and reminders: `rumi_workflow_scheduler_pack`.
- Voice capture, audio, and transcription: `rumi_voice_mobile_pack`.
- CRM, ticket, project, and outbound business execution: `rumi_business_ops_pack`.
- Document parsing and conversion: `rumi_document_intelligence_pack`.

## Pack Contents

The pack includes workflow catalogs, decision/action taxonomy, evidence bundle rules, JSON schemas, local-first policies, recap templates, review checklists, a meeting evidence ledger schema, reviewer profiles, prompts, presets, examples, and an `asset_index.yaml` file that mirrors the manifest index.
