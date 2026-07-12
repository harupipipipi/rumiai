# Overlap Policy

        Owner surface wins first. If a request crosses into an adjacent runtime, this pack emits a handoff packet and does not execute the adjacent action.

        - `workspace_artifact_catalog` -> `handoff_to_rumi_workspace_pack`
- `office_file_rendering` -> `handoff_to_rumi_workspace_pack`
- `pdf_rendering` -> `handoff_to_rumi_workspace_pack`
- `document_understanding` -> `handoff_to_rumi_document_intelligence_pack`
- `data_analysis` -> `handoff_to_rumi_data_analysis_pack`
- `citation_ledger` -> `handoff_to_rumi_evidence_dossier_pack`
- `artifact_app_runtime` -> `handoff_to_rumi_artifact_app_runtime_pack`
- `office_authoring_contract` -> `owned_by_rumi_office_authoring_pack`
- `tool_aliases` -> `prefer_explicit_pack_namespace`
