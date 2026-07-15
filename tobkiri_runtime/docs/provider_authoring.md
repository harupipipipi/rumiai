# Provider Authoring

Provider authoring is manifest-first. An OpenAI-compatible provider must be
addable with a provider manifest plus model definition files; Python provider
code is only required for custom protocols.

Place provider manifests under `extensions/llm/providers/<provider_id>/manifest.json`
or an installed catalog pack that exposes the same extension layout. Place model
definitions under `extensions/llm/providers/<provider_id>/models/*.json`.

For OpenAI-compatible providers, set:

- `category: "llm_provider"`
- `adapter: "openai_compatible"`
- `api_key_env` and optional `base_url_env`
- `default_base_url`
- `default_model` or `default_model_for`
- capability metadata such as `streaming`, `vision`, and `native_tool_calling`

Model capabilities should include `vision`, `thinking`, `tool_calling`, `fast`, and `knowledge_level` where known. Routing depends on these fields to decide whether a request can use a model directly or needs a bridge step.

API keys must stay in the existing secrets/provider-key path. Do not store keys in profile workspaces or provider manifests. Provider tests should cover catalog loading, key status, model capability resolution, routing compatibility, and failure behavior.

The curated provider table is a compatibility fallback for missing legacy
metadata. New providers should not require adding hardcoded rows to runtime code.
