<!-- docs-i18n-links:start -->
[EN](../../defaultspack_boundary.md) | [JP](../ja/defaultspack_boundary.md) | [KR](../ko/defaultspack_boundary.md) | [CN](./defaultspack_boundary.md)
<!-- docs-i18n-links:end -->

# 默认包边界

defaultspack 是 Rumi 的核心运行时包。它提供了通用的执行
包和用户数据的表面，但它不是具体工具的集合，
代理产品、提示、UI 条目或模型目录。

## 属于默认包

- 运行时、代理、注册表加载器、适配器和传输代码。
- 能力契约、模式词汇和通用执行桥。
- Pack/user_data 加载器用于工具、提示、配置文件、预设、UI 清单、
  提供商目录和功能。
- 模块列表、打包请求和策略等核心管理功能
  审查。
- 连接运行时所需的最少启动图。

## 属于包或用户数据

- 面向人工智能的工具定义和具体工具实现。
- 代理行为提示、配置文件、预设、示例和特定产品
  图表。
- 产品简介，例如运营公司。
- 侧边栏项目、设置部分、渲染器、应用程序外壳变体等
  具体的前端声明。
- 提供商和模型目录数据。

## 入门包

默认的本地体验由 defaultspack 和入门包组合而成：

- `rumi_default_tools_pack`：默认工具清单和工具功能。
- `rumi_local_agent_pack`：本地代理提示、配置文件、预设和示例。
- `rumi_operations_company_pack`：运营公司简介、图表、路线和 UI。
- `rumi_reference_ui_pack`：参考侧边栏和面板清单。
- `rumi_model_catalog_pack`：提供商/模型目录清单和提供商 UI。

装载机必须聚合已安装的包和`user_data`并附加
如果可能的话`source_pack_id`。 defaultspack 可能会保留已弃用的兼容性
别名，但新的具体内容应该放在包或用户数据中。
