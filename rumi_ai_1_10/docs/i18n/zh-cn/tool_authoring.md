<!-- docs-i18n-links:start -->
[EN](../../tool_authoring.md) | [JP](../ja/tool_authoring.md) | [KR](../ko/tool_authoring.md) | [CN](./tool_authoring.md)
<!-- docs-i18n-links:end -->

# 工具创作

工具需要清单、可调用函数或工具入口点、风险级别、权限要求、UI 元数据和模型兼容性说明。

功能块是内部可调用单元。工具公开用户可见的功能，并且可以由工具调用模型调用。高风险工具包括文件写入、删除、终端执行、网络突变、浏览器/计算机控制和凭据更改。

工具清单应说明所需的权限、批准需求、输入/输出架构和 UI 标签。在构建 AI 请求之前，必须根据所选模型功能检查工具调用兼容性。
