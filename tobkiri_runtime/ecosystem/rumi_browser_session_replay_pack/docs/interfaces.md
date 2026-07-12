# Interfaces

The primary interface is a set of strict schemas under `schemas/` plus handoff policies under `policies/`. These interfaces describe replay evidence that already exists; this pack does not execute browser actions to produce it.

## Owner Surfaces

- `browser_session_trace_contract`
- `dom_snapshot_evidence_bundle`
- `screenshot_evidence_bundle`
- `browser_event_evidence`
- `replay_manifest_contract`
- `selector_drift_report`
- `redaction_review_receipt`

## Adjacent Owner Handoffs

- `browser_execution` -> `handoff_to_rumi_browser_automation_pack`
- `semantic_dom` -> `handoff_to_rumi_browser_element_pack`
- `browser_transport` -> `handoff_to_rumi_default_tools_pack`
- `audit_logs` -> `handoff_to_defaultspack`
- `form_submission` -> `handoff_to_rumi_browser_form_operator_pack`
- `session_replay_contract` -> `owned_by_rumi_browser_session_replay_pack`
- `redaction_review` -> `owned_by_rumi_browser_session_replay_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`

## Evidence Bundle Contract

Evidence bundles carry IDs, checksums, privacy classes, redaction states, and artifact refs. They must point to semantic DOM evidence from `rumi_browser_element_pack` when element meaning is needed, and to browser automation handoff packets when live interaction is requested.
