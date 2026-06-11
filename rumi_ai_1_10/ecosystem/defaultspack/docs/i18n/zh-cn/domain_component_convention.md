<!-- docs-i18n-links:start -->
[EN](../../domain_component_convention.md) | [JP](../ja/domain_component_convention.md) | [KR](../ko/domain_component_convention.md) | [CN](./domain_component_convention.md)
<!-- docs-i18n-links:end -->

# Defaultspack 域组件约定

Defaultspack 正在转向类似扩展的域组件：一个功能应该
通过在`domain/<category>/<component_id>/`下放置一个文件夹来添加
清单及其拥有的任何小规则、适配器或处理程序。现有的公共 ID，
路线、进口和行为保持稳定，而中央登记处变得更加
发现层和兼容性层。

## 文件夹布局

规范组件文件夹使用此形状：

```text
domain/<category>/<component_id>/
  manifest.json
  rules.py or rules.json
  handler.py / adapter.py / inbound.py / output.py
  README.md
  tests/
```

组件 ID 应该稳定、小写且文件系统安全。公共 ID
清单内可能会保留点、斜杠和历史名称，当这些名称
已经是 API 的一部分。

## 类别命名

使用复数、面向领域的类别：

- `webhooks`
- `integrations`
- `gateway_channels`
- `webhook_url_providers`
- `tools`
- `providers`
- `prompts`
- `templates`
- `input_profiles`
- `output_profiles`
- `audience_policies`
- `transports`
- `ui_surfaces`

类别名称应该描述所有权，而不是实现细节。对于
例如，LINE webhook 默认属于 `webhooks/line`，而 LINE 入站
安全和标准化代码属于`integrations/line`。

## 清单字段

每个组件清单必须包括：

- `id`：稳定组件 ID 或公共 ID。
- `category`：文件夹类别。
- `kind`：类别内的组件类型。
- `version`：组件合同的字符串版本。
- `status`：`experimental`、`stable`或`legacy`。

推荐领域：

- `entrypoints`：运行时代码的导入路径或文件相对入口点。
- `routes`：公共 HTTP 路由元数据、方法和路由 ID。
- `profiles`：组件拥有或公开的输入/输出配置文件 ID。
- `security`：签名、共享秘密、批准、凭证或沙箱策略。
- `ui`：前端分组、图标、命令、面板或目录元数据。
- `policy`：受众、响应、工具或路由规则。
- `capabilities`：提供商、工具、媒体、传输和模式功能。
- `aliases`：解析到此组件的稳定兼容性别名。
- `compatibility`：必须保留的遗留导入、ID、默认值和垫片。
- `conversion_targets`：该组件可以转换或导出到的 id。
- `owner`：拥有模块、团队或维护者提示。
- `source_pack_id`：提供组件的包装。

清单是数据。 Discovery 不得导入处理程序代码或执行任意代码
蟒蛇。仅在选择组件后，运行时层才可以导入入口点
以供使用。

## 入口点

入口点是指向运行时行为的导入字符串或文件本地名称：

```json
{
  "entrypoints": {
    "handler": "domain.integrations.line.inbound:handle_line_webhook",
    "security": "domain.integrations.line.security:verify_signature",
    "adapter": "domain.providers.google.adapter:GoogleProvider"
  }
}
```

兼容性垫片可能会继续导入旧的块模块，但新代码应该
向组件注册表询问所选组件，然后加载特定组件
需要入口点。

## 规则文件

当规则是声明性的时，可以存在于`rules.json`中；当规则是声明性的时，可以存在于`rules.py`中。
规则需要小的辅助函数。规则文件应保留在组件本地
并且不应成为第二个中央登记处。

示例：

- webhook 端点默认值
- 输入和输出配置文件规格
- 观众政策
- 工具审批/风险提示
- 提供商模型默认值
- 提示渲染选项
- 路线元数据
- UI命令分组

## 兼容性别名

别名保留历史公共名称。它们可能包括端点 ID、配置文件
ids、工具 ids、提供者别名、模型别名、路由名称和旧版导入
路径。别名解析必须是明确的和确定性的。

示例：

- 端点 ID：`line-main`、`discord-main`、`slack-main`、`test-webhook`
- 个人资料 ID：`line.default`、`discord.default`、`slack.default`、
  `generic.webhook.default`
- 提供商 ID：`gitlawb-opengateway`
- 型号 ID：`gitlawb-opengateway/mimo-v2.5-pro`，
  `gitlawb-opengateway/mimo-v2-flash`，
  `gitlawb-opengateway/mimo-v2-omni`

## 路由元数据

路由元数据属于在安全时拥有该行为的组件：

```json
{
  "routes": [
    {
      "id": "webhook.line.inbound",
      "path": "/webhooks/line",
      "methods": ["POST"],
      "entrypoint": "domain.integrations.line.inbound:handle_line_webhook"
    }
  ]
}
```

公共路径在迁移过程中不得更改。现有路由表保持为
回退，直到清单支持的路由具有完整的覆盖和测试。

## 提供商和模型元数据

提供者组件拥有提供者元数据、身份验证规则、适配器入口点和
模型默认值。模型目录也可能来自清单支持的兄弟包
例如`rumi_model_catalog_pack`； defaultspack 必须与那些互操作
打包而不是复制或折叠它们。

提供程序组件不应导入工具注册表或工具策略模块。
提供者工具桥接属于知道的编排或代理层
提供商能力和工具执行。

## 提示、配置文件和策略元数据

提示组件拥有提示 ID、提示文本/模板、渲染规则和
提示兼容性别名。输入/输出概况和受众政策应
是清单或规则支持的组件，同时保留现有的注册表 API。

注册表应该加载组件数据，合并用户定义的持久数据，以及
提供兼容性查找。他们不应该增加新的硬编码默认值。

## 迁移规则

- 保留公共 ID、路由、别名、端点 ID、配置文件 ID 和工具 ID
  稳定。
- 将旧进口保留为薄垫片，直到呼叫者移动为止。
- 在删除旧代码之前，最好在旧代码旁边添加清单支持的发现
  代码。
- 在更改运行时之前将默认值移至组件清单或规则文件中
  行为。
- 保持安全和审批行为至少与以前一样严格。
- 对无效组件清单进行软失败并公开诊断。
- 支持发现多个生态系统包。
- 在发现期间不要导入处理程序代码。
- 不要将`rumi_model_catalog_pack`折叠到默认包中。

## 哪些内容不能存在于中央注册表中

中央登记处不应成为以下人员的主要所在地：

- 提供商的端点默认值
- 提供商特定的输入/输出配置文件默认值
- 受众政策默认值
- 提供商许可名单和模型功能元数据
- 工具架构和风险策略
- 特定于集成的签名或响应规则
- 提示文本和提示兼容性别名
- 组件拥有的路由和 UI 元数据

中央文件可以保留兼容性别名、清理、持久性、合并
迁移不完整时的逻辑、诊断和回退行为。
