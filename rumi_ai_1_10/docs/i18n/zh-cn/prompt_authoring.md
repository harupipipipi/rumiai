<!-- docs-i18n-links:start -->
[EN](../../prompt_authoring.md) | [JP](../ja/prompt_authoring.md) | [KR](../ko/prompt_authoring.md) | [CN](./prompt_authoring.md)
<!-- docs-i18n-links:end -->

# 提示创作

提示是被动文本资源。他们描述了人工智能请求的行为，但是
他们不选择模型、发现工具、授予权限、调用提供商或
自行改变运行时状态。

每个提示都需要一个稳定的提示 ID、内容、所有者包或配置文件，并且
棉绒/压实预期。

有效提示优先级为：

1. `profiles/<profile_id>/prompts/`中的配置文件覆盖。
2. `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/`中的个人资料快照。
3. 从defaultspack提示组件或提示扩展中打包默认值。

配置文件覆盖是用户拥有的工作区提示文件，并报告为
`profile_override`层位于`source_chain`中。快照保留包提示
创建配置文件时捕获的版本。包默认值是后备
当不存在特定于配置文件的提示时。

`defaults.prompt.load_effective` 返回选定的源，`source_type`，
`source_chain`、原始`content`和`final_content`。 §鲁米§3§
使用相同的优先级，然后将对话变量渲染到最终的
内容。

不要使用`execution.type="prompt"`创作工具。提示保持被动；使用
当需要渲染提示文本时，来自流程/函数的`defaults.prompt.render`。

及时的 linting 应标记冗余、缺失的角色上下文和代币预算
风险。压实必须保持安全、许可和工具使用限制。
