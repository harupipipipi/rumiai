<!-- docs-i18n-links:start -->
[EN](../../prompt.md) | [JP](../ja/prompt.md) | [KR](../ko/prompt.md) | [CN](./prompt.md)
<!-- docs-i18n-links:end -->

# 提示设计

提示是一个被动的文本层。它存储、验证、解析和渲染
提示模板，但不选择工具、授予权限、选择AI
提供者、调用模型或自行改变聊天状态。

## 有效提示优先级

`defaults.prompt.load_effective`和
`defaults.prompt.resolve_for_conversation` 使用相同的优先级：

1. 从工作区提示目录覆盖配置文件
   `profiles/<profile_id>/prompts/`。
2.个人资料快照来自
   `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/`。
3. 从defaultspack提示组件或提示扩展中打包默认值。

工作区提示文件是正式的`profile_override`层。它是
用户拥有并赢得快照。每一个有效的及时响应都包括
`source_type`、`source`、`source_chain`、`content`和`final_content`所以流动
步骤可以审核哪一层生成了最终文本。

## 函数

- `defaults.prompt.load_effective`返回选定的提示文本和来源
  链，无需渲染对话变量。
- `defaults.prompt.resolve_for_conversation`解决了相同的有效提示
  并从显式 `variables` 加上被动渲染 `{{...}}` 变量
  `context.*`值，例如`context.profile_id`、`context.conversation_id`、
  `context.message_count`和`context.messages`。
- `defaults.prompt.validate_template` 验证模板语法并报告用户
  变量、上下文变量、声明的变量、警告和错误。
- `defaults.prompt.render` 使用提供的内容呈现明确的提示/模板
  变量。

## 创作规则

提示模板可以使用`{{variable}}`和`{{context.variable}}`占位符。
渲染器将​​缺失的变量留在文本中；验证可用于
在流程运行之前检测它们。

提示创作不得创建可执行工具。 `execution.type="prompt"` 是
仅是旧版兼容性路径，不是创作界面。如果一个工作流程
需要渲染提示文本，从流程/函数调用`defaults.prompt.render`。
如果需要工具，请创作`rumi_function`或`capability`工具外观。

提示文件是数据。 Python 提示钩子可读取文件、调用提供程序或
触摸主机功能不属于提示创作；逻辑必须存在
在可信功能和明确的能力授予背后。
