# Interfaces

    The primary interface is a set of strict schemas under `schemas/` plus handoff policies under `policies/`.

`defaultspack` remains the setup, grant, and review authority. This pack only adds office authoring contracts and handoff packets.

    ## Owner Surfaces

    - `slide_deck_authoring_contract`
- `slide_storyboard`
- `slide_layout_brief`
- `speaker_notes_contract`
- `spreadsheet_workbook_authoring_contract`
- `sheet_tab_plan`
- `formula_map`
- `data_validation_plan`
- `doc_authoring_contract`
- `document_outline`
- `style_and_tone_brief`
- `citation_insertion_plan`
- `chart_embedding_contract`
- `pdf_export_plan`
- `office_review_gate`
- `office_suite_handoff_packet`

    ## Adjacent Owner Handoffs

    - `workspace_artifact_catalog` -> `handoff_to_rumi_workspace_pack`
- `office_file_rendering` -> `handoff_to_rumi_workspace_pack`
- `pdf_rendering` -> `handoff_to_rumi_workspace_pack`
- `document_understanding` -> `handoff_to_rumi_document_intelligence_pack`
- `data_analysis` -> `handoff_to_rumi_data_analysis_pack`
- `citation_ledger` -> `handoff_to_rumi_evidence_dossier_pack`
- `artifact_app_runtime` -> `handoff_to_rumi_artifact_app_runtime_pack`
- `office_authoring_contract` -> `owned_by_rumi_office_authoring_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`
