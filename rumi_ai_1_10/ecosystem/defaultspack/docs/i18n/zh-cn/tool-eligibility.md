<!-- docs-i18n-links:start -->
[EN](../../tool-eligibility.md) | [JP](../ja/tool-eligibility.md) | [KR](../ko/tool-eligibility.md) | [CN](./tool-eligibility.md)
<!-- docs-i18n-links:end -->

# 工具资格和被阻止的原因

工具可用性现在在两个地方计算：

1. 聊天/代理准备期间的预提供者过滤
2. 如果过滤工具仍然以某种方式被调用，则执行时拒绝

## 运行时能力快照

每个回合都会记录一个带有标准化标记的`RuntimeCapabilitySnapshot`：

- 输入特征：`input.text`、`input.image`、`input.file`
- 模型功能：`model.text`、`model.image_input`、`model.tool_calling`、
  `model.thinking`，`model.fast`
- 运行时能力
- 政策能力
- 标签

该数据存储在元数据/事件中，而不是注入到正常对话中
文本。

## 工具要求

工具定义可以声明：

- `capability_requirements.requires_all`
- `capability_requirements.requires_any`
- `capability_requirements.forbids`
- `requires_model_capabilities`
- `requires_input_modalities`
- `requires_runtime_capabilities`
- `attachment_policy`
- `supports_attachments`

## 稳定的原因代码

被阻止或拒绝的工具使用稳定的原因代码：

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

执行时拒绝返回结构化结果：

- `status: rejected`
- 提供商安全`code`
- `reason`
- `required`
- `actual`
- `repair_suggestions`
