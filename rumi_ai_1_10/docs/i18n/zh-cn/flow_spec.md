<!-- docs-i18n-links:start -->
[EN](../../flow_spec.md) | [JP](../ja/flow_spec.md) | [KR](../ko/flow_spec.md) | [CN](./flow_spec.md)
<!-- docs-i18n-links:end -->

# 流量规格

流文档具有`flow_id`、可选的`version`和`description`、`inputs`、`outputs`以及有序的`steps`。

规范步骤类型为`function`、`subflow`、`branch`和`parallel`。
旧版处理程序/工具/提示步骤是兼容性路径，不能是
新的 defaultspack 流程的创作界面。

支持的功能步骤字段：

- `id`：稳定步骤标识符。
- `type`：`function`。
- `function`：函数步骤的可调用别名，例如`defaults.ai.complete`。
- `input`：文字值或模板引用。
- `when`：可选条件表达式。
- `output`：步骤写入的变量名称。
- `on_error`：可选的错误处理策略。

配置文件范围的聊天流应在提示、工具、权限、路由、完成、持久性或审核步骤之前加载活动配置文件和工作区。权限过滤器必须在支持工具的 AI 调用之前运行。

提示解决是一个功能步骤，而不是提示执行步骤。标准
聊天转通话`defaults.prompt.load_effective` 或
配置文件工作区之后的`defaults.prompt.resolve_for_conversation`
可用，然后将该文本传递到 AI 请求构造中。有效提示
解决方案使用配置文件覆盖、配置文件快照，然后打包默认优先级。
