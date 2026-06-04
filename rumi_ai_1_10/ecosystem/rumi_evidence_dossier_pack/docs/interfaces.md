# Interfaces

    ## Inputs

    - Local user-supplied artifacts or records emitted by adjacent owner packs.
    - Schema IDs listed in `ecosystem.json`.
    - Evidence IDs, review state, and handoff owner labels.

    ## Outputs

    - Draft packets.
    - Review checklist packets.
    - Handoff packets for owner packs.
    - UI contract templates for host surfaces to render.

    ## Optional Integrations

    - `rumi_research_pack`: Retrieves public sources and research context.
- `rumi_connector_gateway_pack`: Retrieves private connector sources.
- `rumi_data_analysis_pack`: Transforms datasets and computes statistics.
- `rumi_document_intelligence_pack`: Parses and renders documents.
- `rumi_workspace_pack`: Exports dossier files.
- `rumi_model_evals_pack`: Scores model answers against dossiers.

    ## Required Secrets

    None.

    ## Does Not Provide

    - source retrieval
- connector access
- data transformation
- document rendering
- workspace export
- model eval scoring
- web browsing
