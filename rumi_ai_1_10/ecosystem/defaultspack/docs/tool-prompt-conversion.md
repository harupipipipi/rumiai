<!-- docs-i18n-links:start -->
[EN](./tool-prompt-conversion.md) | [JP](./i18n/ja/tool-prompt-conversion.md) | [KR](./i18n/ko/tool-prompt-conversion.md) | [CN](./i18n/zh-cn/tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# Tool / Prompt Reference

Tool and prompt definitions share some vocabulary, but they do not share an
execution boundary.

- Tool authoring uses `rumi_function` or `capability` facades.
- Prompt authoring creates passive text templates.
- New `execution.type="prompt"` tools are not supported.

## Tool To Prompt

Tool definitions can be read as data to generate documentation, examples, or
prompt variables. This does not execute the tool and does not grant any tool
permission.

Typical use:

```python
tool_schema = context["call_handler"]("defaults.tool.schema", {
    "tool_name": "file_read"
})
rendered = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "tool_usage_guide",
    "variables": {"tool_schema": tool_schema}
})
```

## Prompt To Tool

Prompt-to-tool conversion is disabled as an authoring path. If a flow needs
prompt text, call:

- `defaults.prompt.load_effective`
- `defaults.prompt.resolve_for_conversation`
- `defaults.prompt.render`

If a user-visible tool is required, define a normal function/capability facade
that calls the appropriate trusted function. Do not expose prompt rendering as a
prompt execution tool.

## Round Trip

There is no guaranteed tool/prompt round trip. Tool execution metadata,
capability grants, approval policy, and prompt source-chain metadata have
different semantics and should remain in their native systems.
