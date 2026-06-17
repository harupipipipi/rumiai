# Interfaces

## Required Secrets

None.

## Required Network

None by default.

## Grants

`supports_all_ok` is false. This pack does not install runtime tools.

## Inputs

Reviewed local artifacts and source evidence supplied by the user or by an adjacent owner pack. Accepted source types are existing transcript text, meeting notes, agenda text, chat excerpts, and already extracted document text.

## Outputs

Schema-valid decision records, action registers, draft follow-ups, evidence ledgers, recap bundles, and handoff templates.

## Handoffs

- `rumi_connector_gateway_pack`
- `rumi_workflow_scheduler_pack`
- `rumi_voice_mobile_pack`
- `rumi_document_intelligence_pack`
- `rumi_business_ops_pack`

## Does Not Provide

No connector fetching or sending. No calendar booking or reminders. No voice capture or transcription. No business workflow execution. No document parsing. Requests for those actions must be represented as handoff records with evidence and review state.
