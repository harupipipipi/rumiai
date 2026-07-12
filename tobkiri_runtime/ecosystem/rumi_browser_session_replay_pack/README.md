# Rumi Browser Session Replay Pack

`rumi_browser_session_replay_pack` is a declarative setup pack for browser session trace contracts, evidence bundles, replay manifests, selector drift reports, and redaction review. It is inspired by browser automation and session replay workflows, but it does not execute browser actions. It packages observed evidence and emits handoff packets for the runtime owner packs.

## Required Secrets

None.

## What It Provides

- `browser_session_trace_contract`
- `dom_snapshot_evidence_bundle`
- `screenshot_evidence_bundle`
- `browser_event_evidence`
- `replay_manifest_contract`
- `selector_drift_report`
- `redaction_review_receipt`

## Does Not Provide

- browser execution
- semantic DOM interpretation
- browser companion transport
- form submission
- defaultspack audit and grants
- observability metric storage
- connector retrieval

## Handoff Boundaries

- `browser_execution` -> `handoff_to_rumi_browser_automation_pack`
- `semantic_dom` -> `handoff_to_rumi_browser_element_pack`
- `browser_transport` -> `handoff_to_rumi_default_tools_pack`
- `audit_logs` -> `handoff_to_defaultspack`
- `form_submission` -> `handoff_to_rumi_browser_form_operator_pack`
- `session_replay_contract` -> `owned_by_rumi_browser_session_replay_pack`
- `redaction_review` -> `owned_by_rumi_browser_session_replay_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`

## Evidence Rules

- Screenshot evidence is hash-and-reference only; inline binary screenshots are blocked.
- DOM text, typed input evidence, private URLs, console logs, network snippets, account identifiers, session identifiers, credential material, and payment fields must be redacted or blocked before sharing.
- Replay manifests may order observed evidence and name expected page states, but any live browser execution is handed off to `rumi_browser_automation_pack` and transported by `rumi_default_tools_pack`.
