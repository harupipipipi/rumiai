<!-- docs-i18n-links:start -->
[EN](../../model_capabilities.md) | [JP](../ja/model_capabilities.md) | [KR](../ko/model_capabilities.md) | [CN](./model_capabilities.md)
<!-- docs-i18n-links:end -->

# 模型能力

Defaultspack 通过面向路由的功能字段丰富了提供商和配置文件目录。该分数是故意与 rumiai 路由相关的，而不是绝对的模型排名。

关键字段：`supports_vision`、`supports_tool_calling`、`supports_thinking`、`thinking_levels`、`supports_fast`、`speed_tier`、`quality_tier`、`knowledge_level`、`knowledge_band`、`capability_tags`、`allowed_roles`和`recommended_roles`。

使用`defaults.ai.search_models`进行搜索并使用`defaults.ai.get_model_capabilities`检查一个模型。
