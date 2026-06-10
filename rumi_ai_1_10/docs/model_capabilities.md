<!-- docs-i18n-links:start -->
[EN](./model_capabilities.md) | [JP](./i18n/ja/model_capabilities.md) | [KR](./i18n/ko/model_capabilities.md) | [CN](./i18n/zh-cn/model_capabilities.md)
<!-- docs-i18n-links:end -->

# Model Capabilities

Defaultspack enriches provider and profile catalogs with routing-oriented capability fields. The score is intentionally relative to rumiai routing, not an absolute model ranking.

Key fields: `supports_vision`, `supports_tool_calling`, `supports_thinking`, `thinking_levels`, `supports_fast`, `speed_tier`, `quality_tier`, `knowledge_level`, `knowledge_band`, `capability_tags`, `allowed_roles`, and `recommended_roles`.

Search with `defaults.ai.search_models` and inspect one model with `defaults.ai.get_model_capabilities`.
