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

- `defaultspack`: Retrieves sources, handles connector access, transforms datasets, renders documents, exports dossiers, and performs model-scoring handoffs.
- `rumi_default_tools_pack`: Supports manual browser review when a human needs to inspect visible source pages before accepting evidence.

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
