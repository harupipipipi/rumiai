<!-- docs-i18n-links:start -->
[EN](./ui_agent_experience_design.md) | [JP](./i18n/ja/ui_agent_experience_design.md) | [KR](./i18n/ko/ui_agent_experience_design.md) | [CN](./i18n/zh-cn/ui_agent_experience_design.md)
<!-- docs-i18n-links:end -->

# UI Agent Experience Design

The UI is a replaceable shell built from parts.

Expected panels:

- chat
- plan
- tool calls
- file tree
- diff viewer
- terminal
- artifacts
- memory
- project settings
- approval dialog
- model selector
- compact button
- run history
- source cards

The frontend receives capability, renderer, settings, model, tool, and account metadata from catalog APIs. It should not hard-code pack internals.
