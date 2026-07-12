# Handoff Packet

- Owner pack: {{ owner_pack }}
- Reason: {{ reason }}
- Source artifacts: {{ source_artifacts }}
- Evidence IDs: {{ evidence_ids }}
- Source note IDs: {{ source_note_ids }}
- Source span IDs: {{ source_span_ids }}
- Uncertainty or limitations: {{ uncertainty }}
- Human review required: true

## Evidence

{{ evidence_summary }}

## Handoff

{{ handoff_instruction }}

## Boundary Controls

- This pack performed external action: false
- Forbidden action requested: {{ forbidden_action_requested }}
- Reviewer decision required before owner execution: true
- Return path for owner output: {{ return_artifact_path }}
