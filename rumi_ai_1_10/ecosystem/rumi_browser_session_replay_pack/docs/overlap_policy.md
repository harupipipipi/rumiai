# Overlap Policy

Owner surface wins first. If a request crosses into an adjacent runtime, this pack emits a handoff packet and does not execute the adjacent action.

- `browser_execution` -> `handoff_to_rumi_browser_automation_pack`
- `semantic_dom` -> `handoff_to_rumi_browser_element_pack`
- `browser_transport` -> `handoff_to_rumi_default_tools_pack`
- `audit_logs` -> `handoff_to_defaultspack`
- `form_submission` -> `handoff_to_rumi_browser_form_operator_pack`
- `session_replay_contract` -> `owned_by_rumi_browser_session_replay_pack`
- `redaction_review` -> `owned_by_rumi_browser_session_replay_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`

This pack owns replay evidence contracts and redaction review. It does not execute browser actions, interpret semantic DOM, operate browser transport, submit forms, or replace defaultspack audit and grant enforcement.
