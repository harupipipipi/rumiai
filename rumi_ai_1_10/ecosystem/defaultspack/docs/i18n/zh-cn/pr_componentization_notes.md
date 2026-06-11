<!-- docs-i18n-links:start -->
[EN](../../pr_componentization_notes.md) | [JP](../ja/pr_componentization_notes.md) | [KR](../ko/pr_componentization_notes.md) | [CN](./pr_componentization_notes.md)
<!-- docs-i18n-links:end -->

# PR 注释：Defaultspack 组件化

## 总结

此 PR 将 defaultspack 移向类似扩展的组件文件夹，同时保留现有的公共行为。组件清单现在涵盖 Webhook 默认值、外部配置文件、集成、网关通道、URL 提供程序、工具、提供程序、提示、路由和 UI 界面。

## 架构目标

添加表面应该成为文件放置工作流程：

```text
domain/<category>/<component_id>/manifest.json
```

中央注册表保留兼容性和发现层。他们不应该重新获得硬编码的连接器/配置文件/提供程序/工具/提示默认值。

## 新组件文件夹约定

新的域表面应作为文件放置组件添加：

```text
domain/<category>/<component_id>/
  manifest.json
  rules.py or rules.json
  handler.py / adapter.py / inbound.py / output.py
  README.md optional
  tests optional
```

清单是发现合同。它携带 ID、类别/种类、版本/状态、入口点、路由、配置文件、安全性、UI、策略、功能、别名、兼容性元数据、转换目标和源包所有权（如果有用）。

## PR #92 兼容性

- Gitlawb OpenGateway 提供商 ID 仍为 `gitlawb-opengateway`。
- Gitlawb OpenGateway 模型 ID 保留：
  - `gitlawb-opengateway/mimo-v2.5-pro`
  - `gitlawb-opengateway/mimo-v2-flash`
  - `gitlawb-opengateway/mimo-v2-omni`
- 保留无键行为、默认基本 URL 行为、浏览器用户代理行为和固定模型白名单行为。
- MiMo Omni 保留经过验证的图像元数据。
- `rumi_model_catalog_pack`提供商/模型清单被保留并保持清单支持。
- 保留 LINE Biz webhook 确认/后台处理，包括确认文本、回复令牌重用抑制、当前回合聊天历史记录模式、物理点击提示行为、来源/源记录、签名验证和受众策略行为。
- `rumi_default_tools_pack` 中保留了浏览器/计算机驱动程序的安全性，包括仅可见屏幕的行为、前台防护、需要批准的物理操作、URL 方案限制和后备顺序。

## 各阶段发生了什么变化

1. 记录了域组件文件夹约定。
2. 添加了共享清单发现、验证、注册表、别名、诊断和多包根。
3. 将 webhook 端点/安全默认值移至组件清单中。
4. 将输入配置文件、输出配置文件和受众策略移至组件支持的清单中。
5. 在组件入口点后面拆分 LINE、Discord 和 Slack 集成，同时保留块垫片。
6. 组件化网关通道和带有旧版导入垫片的 Webhook URL 提供程序。
7. 添加了清单支持的工具/浏览器/计算机组件元数据，包括`rumi_default_tools_pack`。
8. 将提供程序/模型元数据移至提供程序组件中，包括 Gitlawb OpenGateway。
9. 组件化的提示和模板界面。
10. 从组件清单加载路由和 UI 表面元数据。
11.添加了护栏和兼容性测试，以防止重新集中组件默认值。
12. 添加了迁移文档、PR 说明和最终质量检查。

## 兼容性保证

- 现有端点 ID 保持稳定：`line-main`、`discord-main`、`slack-main`、`test-webhook`。
- 现有配置文件 ID 保持稳定：`line.default`、`discord.default`、`slack.default`、`generic.webhook.default`。
- 现有提供者别名、路由路径、工具 ID、提示 ID 和旧导入路径通过兼容层仍然可用。
- 组件发现在错误清单上软失败并报告诊断而不是执行任意代码。
- 批准和安全行为保留在现有策略/执行者路径中。

## 保留现有 ID 和路由

- 端点 ID 仍为`line-main`、`discord-main`、`slack-main`和`test-webhook`。
- 配置文件 ID 仍为`line.default`、`discord.default`、`slack.default`和`generic.webhook.default`。
- 公共 webhook、设置、UI、提供程序、提示和工具路由路径仍由现有路由表支持，并将清单支持的路由添加为元数据/发现，而不是替换公共路径。
- 提供程序别名、工具 ID、提示 ID、端点 ID 和旧的块/导入路径通过兼容性填充程序保留。

## 测试运行

-`python -m pytest rumi_ai_1_10/tests/test_defaultspack_webhook_endpoints.py rumi_ai_1_10/tests/test_defaultspack_external_send_tool.py rumi_ai_1_10/tests/test_defaultspack_tool_policy.py rumi_ai_1_10/tests/test_defaultspack_ui_registry.py rumi_ai_1_10/tests/test_defaultspack_mcp_registry.py rumi_ai_1_10/tests/test_defaultspack_agent_service_plan.py rumi_ai_1_10/tests/test_defaultspack_opengateway_provider.py rumi_ai_1_10/tests/test_defaultspack_google_provider.py rumi_ai_1_10/tests/test_defaultspack_line_origin_regression.py rumi_ai_1_10/tests/test_browser_cdp_driver.py rumi_ai_1_10/tests/test_browser_computer_security_windows.py rumi_ai_1_10/tests/test_computer_fallback_order.py rumi_ai_1_10/tests/test_defaultspack_domain_components.py rumi_ai_1_10/tests/test_defaultspack_external_components.py rumi_ai_1_10/tests/test_defaultspack_integration_components.py rumi_ai_1_10/tests/test_defaultspack_gateway_url_components.py rumi_ai_1_10/tests/test_defaultspack_tool_components.py rumi_ai_1_10/tests/test_defaultspack_provider_components.py rumi_ai_1_10/tests/test_defaultspack_prompt_components.py rumi_ai_1_10/tests/test_defaultspack_route_ui_components.py rumi_ai_1_10/tests/test_defaultspack_component_guardrails.py -q`：373通过。
- `python -m compileall rumi_ai_1_10/ecosystem/defaultspack`：通过。
- `python .github/scripts/quality_gate_nonregression.py --base-ref origin/master`：通过，Ruff 不变，mypy 债务减少。
- `python -m pytest rumi_ai_1_10/tests -q`：4339 项通过，20 项跳过。

## 已知风险

- PR 有意保留兼容性垫片，因此在下游导入和调用站点迁移之前会保留一些后备表。
- 组件元数据和遗留注册表共存；未来的清理工作应该仅在覆盖范围更广之后才消除重复的后备声明。
- 发现现在跨越多个生态系统包，因此即使运行时行为继续，格式错误的第三方清单也可以显示诊断。

## 回滚注意事项

每个阶段都是一个连贯的提交。如果需要，恢复相关阶段提交，同时保留后续文档/测试作为指导。兼容性填充程序使回滚本地化，因为旧的导入和路由路径仍然存在。

## 后续清理

- 随着覆盖范围的扩大，继续将旧的后备表移至清单中。
- 展开剩余提供者/目录元数据的组件清单。
- 为路由/组件诊断添加更丰富的 UI。
- 仅在下游导入迁移后才逐渐停用兼容性垫片。
