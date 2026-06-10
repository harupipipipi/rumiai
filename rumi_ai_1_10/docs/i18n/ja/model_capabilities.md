<!-- docs-i18n-links:start -->
[EN](../../model_capabilities.md) | [JP](./model_capabilities.md) | [KR](../ko/model_capabilities.md) | [CN](../zh-cn/model_capabilities.md)
<!-- docs-i18n-links:end -->

# モデルの機能

Defaultspack は、ルーティング指向の機能フィールドを使用してプロバイダーとプロファイルのカタログを強化します。スコアは、絶対的なモデル ランキングではなく、意図的に rumiai ルーティングに相対的なものです。

キーフィールド: `supports_vision`、`supports_tool_calling`、`supports_thinking`、`thinking_levels`、`supports_fast`、`speed_tier`、`quality_tier`、`knowledge_level`、`knowledge_band`、`capability_tags`、`allowed_roles`、および `recommended_roles`。

`defaults.ai.search_models`で検索し、`defaults.ai.get_model_capabilities`で1つのモデルを検査します。
