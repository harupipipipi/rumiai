<!-- docs-i18n-links:start -->
[EN](../../tool-prompt-conversion.md) | [JP](../ja/tool-prompt-conversion.md) | [KR](../ko/tool-prompt-conversion.md) | [CN](./tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# 工具/提示参考

工具和提示定义共享一些词汇，但它们不共享
执行边界。

- 工具创作使用`rumi_function`或`capability`外观。
- 提示创作创建被动文本模板。
- 不支持新的`execution.type="prompt"`工具。

## 提示工具

工具定义可以作为数据读取以生成文档、示例或
提示变量。这不会执行该工具并且不会授予任何工具
许可。

典型用途：

```python
tool_schema = context["call_handler"]("defaults.tool.schema", {
    "tool_name": "file_read"
})
rendered = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "tool_usage_guide",
    "variables": {"tool_schema": tool_schema}
})
```

## 提示工具

禁用提示到工具转换作为创作路径。如果流量需要
提示文字，拨打：

- `defaults.prompt.load_effective`
- `defaults.prompt.resolve_for_conversation`
- `defaults.prompt.render`

如果需要用户可见的工具，请定义一个普通的功能/能力外观
调用适当的可信函数。不要将提示渲染公开为
提示执行工具。

## 往返

不保证工具/快速往返。工具执行元数据，
能力授予、审批政策和及时的源链元数据
不同的语义，应保留在其本机系统中。
