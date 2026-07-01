# Provider and Model Metadata Contract

Provider/model metadata has one owner for each kind of fact:

- Provider component manifests (`domain/providers/*/manifest.json`) own discovery,
  credentials, entrypoints, catalog labels, and `catalog_features`.
  They must not define `api_surface` or model capability truth.
- Provider capability manifests
  (`domain/ai_client/capabilities/manifests/*.json`) own provider API surface:
  API family, accepted content block shapes, request params, schema/tool-call
  request shapes, roles, and provider quirks.
- Model manifests (`models.json` and llm model extension JSON) own model ability:
  canonical `capabilities`, `modalities`, `thinking`, `routing`, context window,
  pricing, and model-specific metadata.
- Runtime normalizers may emit legacy fields such as `supports_vision`,
  `supports_tool_calling`, `max_context`, and `defaults`, but those fields are
  compatibility output, not bundled source truth.

Canonical model capability keys are:

- `text_input`
- `image_input`
- `audio_input`
- `text_output`
- `tool_calling`
- `parallel_tool_calls`
- `json_schema`
- `structured_output`
- `thinking`
- `streaming`

Legacy aliases such as `vision`, `reasoning`, `tool_calls`, `json_mode`,
`response_format`, and list-shaped `capabilities` are accepted only at ingestion
or profile compatibility boundaries. Bundled source JSON must use the canonical
keys above.

`context_window` is the bundled source field for model context size. `max_context`
and `max_context_tokens` may still be emitted by normalized APIs for frontend
compatibility, but source JSON must not write all three.
