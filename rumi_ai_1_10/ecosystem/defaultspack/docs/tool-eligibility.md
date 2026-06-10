<!-- docs-i18n-links:start -->
[EN](./tool-eligibility.md) | [JP](./i18n/ja/tool-eligibility.md) | [KR](./i18n/ko/tool-eligibility.md) | [CN](./i18n/zh-cn/tool-eligibility.md)
<!-- docs-i18n-links:end -->

# Tool Eligibility And Blocked Reasons

Tool availability is now computed in two places:

1. pre-provider filtering during chat/agent preparation
2. execution-time rejection if a filtered tool is somehow still called

## Runtime capability snapshot

Each turn records a `RuntimeCapabilitySnapshot` with normalized tokens:

- input traits: `input.text`, `input.image`, `input.file`
- model capabilities: `model.text`, `model.image_input`, `model.tool_calling`,
  `model.thinking`, `model.fast`
- runtime capabilities
- policy capabilities
- tags

This data is stored in metadata/events, not injected into normal conversation
text.

## Tool requirements

Tool definitions may declare:

- `capability_requirements.requires_all`
- `capability_requirements.requires_any`
- `capability_requirements.forbids`
- `requires_model_capabilities`
- `requires_input_modalities`
- `requires_runtime_capabilities`
- `attachment_policy`
- `supports_attachments`

## Stable reason codes

Blocked or rejected tools use stable reason codes:

- `missing_capability`
- `missing_input`
- `model_unsupported`
- `disabled_by_user`
- `disabled_by_policy`
- `requires_approval`
- `not_connected_to_profile`
- `requires_trusted_workspace`
- `missing_api_key`
- `attachment_not_supported`
- `risk_blocked`

Execution-time rejection returns a structured result with:

- `status: rejected`
- provider-safe `code`
- `reason`
- `required`
- `actual`
- `repair_suggestions`
