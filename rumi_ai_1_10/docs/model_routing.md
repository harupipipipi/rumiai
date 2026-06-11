<!-- docs-i18n-links:start -->
[EN](./model_routing.md) | [JP](./i18n/ja/model_routing.md) | [KR](./i18n/ko/model_routing.md) | [CN](./i18n/zh-cn/model_routing.md)
<!-- docs-i18n-links:end -->

# Model Routing

Model routing starts from the user's preferred model group, then checks images, files, requested tools, requested thinking level, speed hints, and utility model settings.

The router returns `selected_model`, `original_model`, `selected_group`, `reason_codes`, `warnings`, `bridge_required`, `bridge_plan`, and `utility_models`. Tool selection remains advisory; existing permission and grant checks are still the final authority.
