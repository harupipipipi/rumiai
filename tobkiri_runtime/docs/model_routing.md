# Model Routing

Model routing starts from the user's preferred model group, then checks images, files, requested tools, requested thinking level, speed hints, and utility model settings.

The router returns `selected_model`, `original_model`, `selected_group`, `reason_codes`, `warnings`, `bridge_required`, `bridge_plan`, and `utility_models`. Tool selection remains advisory; existing permission and grant checks are still the final authority.
