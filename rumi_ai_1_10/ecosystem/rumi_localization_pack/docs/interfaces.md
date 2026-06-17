# Interfaces

## Required Secrets

None.

## Required Network

None by default.

## Grants

`supports_all_ok` is false. This pack does not install runtime tools.

## Inputs

Reviewed local artifacts and source evidence supplied by the user or by an adjacent owner pack. Required evidence includes source locale, target locale, locale pair, source segment ID, target segment ID, source excerpt, target excerpt, and reviewer confidence.

## Outputs

Schema-valid locale issue records, localization review records, policy-reviewed checklists, evidence ledgers, protected-term exception requests, and handoff templates.

## Handoffs

- `rumi_document_intelligence_pack`
- `rumi_frontend_design_pack`
- `rumi_workspace_pack`
- `rumi_connector_gateway_pack`

## Does Not Own

- Document parsing or document mutation.
- Frontend layout, truncation fixes, visual replay, or browser automation.
- Workspace file generation or export.
- Connector send, publish, sync, or delivery.
- Generic QA scoring or model evals.
