# Rumi Evidence Dossier Pack

Declarative evidence dossier contracts for source registry, claim graphs, evidence links, contradiction review, citation ledgers, reviewer queues, quality labels, and export manifests.

This setup pack makes Rumi more customizable by adding a domain contract that can be selected independently from defaultspack. It is intentionally local-first, declarative, and reviewable: it creates schemas, workflow packets, quality gates, and handoff records instead of executing adjacent runtime actions.

## Provides

- source_registry
- source_quality_label
- claim_evidence_graph
- evidence_link_contract
- contradiction_review_contract
- citation_ledger
- reviewer_queue
- dossier_export_manifest

## Does Not Provide

- source retrieval
- connector access
- data transformation
- document rendering
- workspace export
- model eval scoring
- web browsing

## Required Secrets

None. Network is denied by default and the pack contains no executable runtime code.

## Defaultspack Promotion

Not eligible by default. Promotion requires:

- requires_shared_source_provenance_object
- requires_citation_required_response_mode
- retrieval_owned_elsewhere
- document_rendering_owned_elsewhere
- must_prove_contradiction_blocking_cases

## Overlap Rule

If another pack can perform a step, Rumi should prefer the narrower owner surface. This pack emits a Handoff packet whenever the request crosses into retrieval, connector IO, data transformation, document rendering, workspace export, or model scoring owned by defaultspack. Human browser inspection can be escalated separately to `rumi_default_tools_pack`.
