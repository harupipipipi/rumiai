# Rumi SOP Mining Pack

Declarative trace-to-SOP, checklist, runbook, and human-approved workflow recipe pack.

## Provides

This pack owns trace_redaction_contract, trace_schema, sop_extraction, assumption_log, runbook_template, human_approval_gate, source consent review, and non-execution boundary review. It gives Rumi a customizable, local-first contract for this domain without silently taking over adjacent runtime authority.

## Does Not Provide

This pack does not provide automation execution, browser control, computer control, schedule creation, tool creation or invocation, live trace capture, message delivery, or long-term observability ledger storage. Those surfaces are routed through setup-pack overlap policy and explicit handoff packets.

## Human Approval Gate

Promoted workflow recipes must include redaction completion, source consent basis, a named human approver role, an approval record reference, and an owner handoff for every adjacent runtime surface.

## Required Secrets

None.

## Network

None by default.

## Handoff Owners

- `rumi_observability_pack`
- `rumi_agentic_qa_pack`
- `rumi_security_review_pack`
- `rumi_browser_automation_pack`
- `rumi_workflow_scheduler_pack`
- `rumi_computer_control_pack`
