# Interfaces

## Required Secrets

None.

## Required Network

None by default.

## Grants

`supports_all_ok` is false. This pack does not install runtime tools.

## Inputs

Reviewed local artifacts and source evidence supplied by the user or by an adjacent owner pack. Inputs must be normalized to `schemas/trace_evidence_record.schema.json` with redaction state, consent basis, scope boundary, and `raw_payload_included` set to false.

## Outputs

Schema-valid trace records, schema-valid SOP records, policy-reviewed checklists, evidence ledgers, runbook drafts, and handoff templates. Outputs do not execute automation, browser control, computer control, schedule creation, observability storage, or tool invocation.

## Handoffs

- `rumi_observability_pack`
- `rumi_agentic_qa_pack`
- `rumi_security_review_pack`
- `rumi_browser_automation_pack`
- `rumi_workflow_scheduler_pack`
- `rumi_computer_control_pack`
