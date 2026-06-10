<!-- docs-i18n-links:start -->
[EN](./tool_authoring.md) | [JP](./i18n/ja/tool_authoring.md) | [KR](./i18n/ko/tool_authoring.md) | [CN](./i18n/zh-cn/tool_authoring.md)
<!-- docs-i18n-links:end -->

# Tool Authoring

A tool needs a manifest, callable function or tool entrypoint, risk level, permission requirements, UI metadata, and model compatibility notes.

Function blocks are internal callable units. Tools expose user-visible capabilities and may be invoked by tool-calling models. High-risk tools include file writes, deletion, terminal execution, network mutation, browser/computer control, and credential changes.

Tool manifests should state required permissions, approval needs, input/output schemas, and UI labels. Tool-calling compatibility must be checked against selected model capabilities before the AI request is built.
