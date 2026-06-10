<!-- docs-i18n-links:start -->
[EN](./prompt_authoring.md) | [JP](./i18n/ja/prompt_authoring.md) | [KR](./i18n/ko/prompt_authoring.md) | [CN](./i18n/zh-cn/prompt_authoring.md)
<!-- docs-i18n-links:end -->

# Prompt Authoring

Prompts are passive text resources. They describe behavior for an AI request, but
they do not select models, discover tools, grant permissions, call providers, or
mutate runtime state on their own.

Each prompt needs a stable prompt id, content, owner pack or profile, and
lint/compaction expectations.

Effective prompt priority is:

1. Profile override in `profiles/<profile_id>/prompts/`.
2. Profile snapshot in `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/`.
3. Pack default from defaultspack prompt components or prompt extensions.

Profile overrides are user-owned workspace prompt files and are reported as the
`profile_override` layer in `source_chain`. Snapshots preserve the pack prompt
version captured when the profile was created. Pack defaults are the fallback
when no profile-specific prompt exists.

`defaults.prompt.load_effective` returns the selected source, `source_type`,
`source_chain`, raw `content`, and `final_content`. `defaults.prompt.resolve_for_conversation`
uses the same priority and then renders conversation variables into the final
content.

Do not author tools with `execution.type="prompt"`. Prompts remain passive; use
`defaults.prompt.render` from a flow/function when rendered prompt text is needed.

Prompt linting should flag redundancy, missing role context, and token budget
risk. Compaction must preserve safety, permission, and tool-use constraints.
