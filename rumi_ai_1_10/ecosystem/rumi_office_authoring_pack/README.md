# Rumi Office Authoring Pack

    `rumi_office_authoring_pack` is a declarative setup pack for Slides, Sheets, Docs, chart, citation, and PDF export authoring contracts. It adds schemas, policies, examples, review gates, and handoff packets while leaving runtime execution to the existing owner packs.

    ## Required Secrets

    None.

    ## What It Provides

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

    ## Does Not Provide

    - workspace broad artifact catalog and lifecycle
- document parsing and redline understanding
- data cleaning and statistical analysis
- claim graph and citation ledger credibility
- PPTX DOCX XLSX PDF rendering
- artifact app runtime approval
- external retrieval and connectors

    ## Handoff Boundaries

    - `workspace_artifact_catalog` -> `handoff_to_rumi_workspace_pack`
- `office_file_rendering` -> `handoff_to_rumi_workspace_pack`
- `pdf_rendering` -> `handoff_to_rumi_workspace_pack`
- `document_understanding` -> `handoff_to_rumi_document_intelligence_pack`
- `data_analysis` -> `handoff_to_rumi_data_analysis_pack`
- `citation_ledger` -> `handoff_to_rumi_evidence_dossier_pack`
- `artifact_app_runtime` -> `handoff_to_rumi_artifact_app_runtime_pack`
- `office_authoring_contract` -> `owned_by_rumi_office_authoring_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`
