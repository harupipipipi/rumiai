<!-- docs-i18n-links:start -->
[EN](./prompt_compaction.md) | [JP](./i18n/ja/prompt_compaction.md) | [KR](./i18n/ko/prompt_compaction.md) | [CN](./i18n/zh-cn/prompt_compaction.md)
<!-- docs-i18n-links:end -->

# Prompt Linting And Compaction

Prompt linting detects duplicate sections, token budget pressure, and must-keep safety or permission text. Compaction suggests a shorter prompt while preserving sections that mention safety, approvals, permissions, secrets, or credentials.

Pack prompts are not rewritten destructively; consumers should store accepted suggestions in profile workspace configuration.
