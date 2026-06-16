# Architecture

`rumi_sop_mining_pack` is declarative. It ships catalogs, schemas, policies, templates, examples, prompts, profiles, and presets. It registers no tools and grants no broad permissions.

Owned surfaces: trace_redaction_contract, sop_extraction, assumption_log, runbook_template, human_approval_gate.

Expanded owner surfaces: trace_schema, source_consent_review, and non_execution_boundary_review.

Excluded surfaces: automation execution, browser control, computer control, schedule creation, live trace capture, long-term observability ledger storage, tool creation, tool invocation, and message delivery. The pack can document a repeatable process only after evidence already exists and after redaction has been reviewed.
