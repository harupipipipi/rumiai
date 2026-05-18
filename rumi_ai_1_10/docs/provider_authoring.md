# Provider Authoring

A provider needs a manifest, model catalog entries, capability metadata, API-key handling, and tests.

Model capabilities should include `vision`, `thinking`, `tool_calling`, `fast`, and `knowledge_level` where known. Routing depends on these fields to decide whether a request can use a model directly or needs a bridge step.

API keys must stay in the existing secrets/provider-key path. Do not store keys in profile workspaces or provider manifests. Provider tests should cover catalog loading, key status, model capability resolution, routing compatibility, and failure behavior.
