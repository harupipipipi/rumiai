# Interfaces

## Inputs

- `connector_id`: Slack, Gmail, Drive, GitHub, Notion, calendar, messaging, or custom connector.
- `source_channel`: Where the request arrived.
- `data_class`: Message, file, calendar event, issue, PR, spreadsheet, doc, or attachment.
- `scope_card`: Requested OAuth/API scope and reason.
- `handoff_target`: Agent service, workspace artifact, scheduler, security review, or user reply.

## Outputs

- `connector_handoff`: Normalized request with provenance and trust labels.
- `scope_review_card`: Human-readable permission review artifact.
- `inbound_risk`: prompt_injection, spoofing, sensitive_data, untrusted_attachment, or none.
- `delivery_contract`: Reply/draft/export target and delivery constraints.

## Required Secrets

None.
