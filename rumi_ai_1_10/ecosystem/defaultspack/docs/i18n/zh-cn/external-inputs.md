<!-- docs-i18n-links:start -->
[EN](../../external-inputs.md) | [JP](../ja/external-inputs.md) | [KR](../ko/external-inputs.md) | [CN](./external-inputs.md)
<!-- docs-i18n-links:end -->

# 外部输入

外部输入是从本地 UI 之外的系统输入 Rumi 的消息：
webhooks、聊天平台、自动化回调、隧道、本地脚本或
未来的连接器。它们都使用相同的框架边界：

```text
provider payload
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> dispatch_input / submit_input
  -> ResponsePromptPolicy
  -> ResponsePlanner
  -> ResponseAdapter
```

目标是将提供商的详细信息保持在边缘。聊天、代理和流程逻辑
应接收标准化输入，而不是 Slack、Discord、LINE 或特定于隧道的输入
有效负载。

## 核心类型

`ExternalEvent` 是规范化的入库记录。它包含稳定的字段：
§鲁米§0§，§鲁米§1§，§鲁米§2§，§鲁米§3§，§鲁米§4§，§鲁米§5§，§鲁米§6§，
`verified`，并编辑`metadata`。提供者特定的标识符被吸收
融入这些原则。原始请求主体可用于签名检查，但是
原始秘密和令牌值永远不会在返回的事件对象中公开
UI、日志或文档。

`AudiencePolicy`决定是否允许事件进入鲁米。政策可以
按提供商、团队、渠道、用户、提及方式、直接消息状态划分的门，
速率限制或需要验证。政策输出明确：`allow`，
`ignore`、`deny`或`needs_approval`。

`InputProfile` 将允许的事件映射到`RumiInputEnvelope`：角色、输入文本、
聊天外部密钥/标题/模型、源元数据、参数和工具。它执行
仅转换；它不决定是否允许某个事件。

输入和输出配置是分开的。输入配置文件回答“发生了什么
以及如何进入聊天？”。输出配置文件回答“在哪里可以响应
走哪条交通工具？”。LINE 存在内置输入模板，
Discord、Slack 和通用 Webhooks；自定义模板可以通过注册
`/api/external/templates` 或置于`user_data/shared/external_io_templates` 中。
内置模板公开`setup_mode: copy_paste_select`：UI 呈现
模板/配置文件/提供商选择以及可复制的路由路径和仅粘贴令牌
或目标字段。自由格式的 YAML/配置文件编辑属于自定义。
对于 LINE、Slack 和 Discord 交互等 Webhook 提供商，
外部输入面板包括一个临时公共 URL 启动器。云耀
快速隧道按钮为所选路由路径创建临时公共 URL，
例如`/api/integrations/line/webhook`，因此用户可以粘贴完整的 URL
进入提供商仪表板。

`submit_input` 是配置文件转换后的兼容性入口点。
现在，它在内部转发到`dispatch_input`，该路由
`RumiInputEnvelope`，作者：`delivery.action_id`。

`ResponsePlanner` 将运行时结果转换为提供者中立的响应
计划。它决定是否回复、仅确认、推迟、分割、截断或
跳过。

`ResponsePromptPolicy` 是规划器之前的可选的仅规划层。
它可以选择诸如`reply_text`、`store_only`、`run_browser_use`、
`run_python`，或`ask_for_approval`，但它只返回一个决策对象。
工具执行仍然经过正常的工具策略、批准和转向
跑步者路径。

`ResponseAdapter` 通过特定于提供商的服务提供并交付该计划
表面，例如 Slack 线程、LINE 回复令牌、Discord 交互响应，
或通用 Webhook 响应。

默认输入模板设置`include_source_context: true`。鲁米说出了回合
之前输入来自 LINE、Discord、Slack 或其他提供商的跑步者
用户的文本，同时将原始令牌和请求机密保留在提示之外。

## 活动合约

标准化事件示例：

```json
{
  "provider": "line",
  "workspace": {
    "type": "line_destination",
    "id": "destination-id"
  },
  "scope": {
    "type": "group",
    "id": "C123"
  },
  "actor": {
    "type": "user",
    "id": "U123"
  },
  "conversation": {
    "type": "external",
    "id": "line:group:C123"
  },
  "event": {
    "id": "evt_01",
    "message_id": "msg_01",
    "type": "message",
    "message_type": "text"
  },
  "payload": {
    "type": "message"
  },
  "verified": true,
  "metadata": {
    "reply_token": "short-lived-provider-handle"
  }
}
```

短暂的提供者回复句柄保存在元数据中以供适配器使用。他们
不得将其视为长期配置的令牌或显示回 UI。

## 处理规则

1. 在解析信任敏感字段之前验证请求。
2. 将提供商有效负载标准化为`ExternalEvent`。
3. 使用`provider + event_id`删除重复项。
4. 评估`AudiencePolicy`。
5. 选择`InputProfile`。
6. 致电`submit_input`。
7. （可选）运行`ResponsePromptPolicy` 以生成安全操作决策。
8. 运行`ResponsePlanner`。
9. 通过`ResponseAdapter`交付。

如果任何步骤拒绝该事件，适配器应返回提供者期望的
无需创建聊天消息即可确认。

快速路由的响应操作仅是计划性的：`response_prompt` 可能会返回
`ResponsePlan`决定，但外部交付仍然通过
适配器路径，允许的操作、敏感性、功能和批准
要求再次检查。

## 局部第一边界

默认情况下，外部输入支持不会使本地运行时公开。的
除非明确配置，否则网关和 HTTP 传输绑定到环回
否则允许。公共 URL 提供程序只是一个可替换的边缘组件。
Cloudflare Quick Tunnel 可以在开发过程中使用，但它不是
核心架构，并且必须保持与另一个隧道的可交换性，反向
代理或平台入口。

## 内置设置形状

内置 UI 特意是一个引导式设置，而不是 YAML 编辑器：

- `External Input`：选择提供商/模板/配置文件，生成或复制
  webhook URL，然后选择默认响应行为。
- `External Output`：选择发送模式和输出模板，粘贴屏蔽
  外部令牌，并粘贴非秘密目标 ID，例如 Discord `channel_id`。
- `External Custom`：注册或删除自定义模板/配置文件，并保留
  自由格式的响应提示，例如计算机使用的浏览器工作流程。

LINE 使用提供商创建的 Webhook URL 以及 `Channel Secret` 验证和
`Channel Access Token`回复。 Discord 有两种出站模式：`Bot + Channel`
使用机器人令牌和`channel_id`，而`Webhook URL`使用通道 webhook
URL 作为屏蔽的外部令牌。 Slack 使用事件请求 URL、签名
秘密、机器人令牌和线程感知`chat.postMessage`。

## 安全注意事项

- Webhook 端点管理和公共 URL 创建路由被视为
  local-admin 敏感路由并需要本地身份验证防护。
- 外部入站 webhook 路由仍可从外部访问，但每个端点
  预计将强制执行提供者签名或共享秘密验证。
- 新创建的通用 Webhook 端点默认为禁用+shared_secret
  除非另有明确配置。
- Cloudflare Quick Tunnel 只是一个可交换的公共 URL 提供商。它不是一个
  安全边界；端点安全和本地管理路由防护仍然存在
  需要。

## 已知限制

- 此 PR 中的 LINE 和 Discord 适配器是 MVP 文本响应适配器，而不是
  完整的生产机器人实施。
- LINE 非文本消息目前已标准化为占位符文本。
- 故意减少不和谐交互处理；完全延期/后续
  交互行为应该在后续的 PR 中处理。
- Cloudflare Quick Tunnel 只是一个可交换的公共 URL 提供商。不应该
  被视为安全边界；端点安全和本地管理路由
  仍然需要警卫。

## 当前的 Defaultspack 路由

当前的集成路线是特定于提供商的适配器，应该融合
在上面的框架边界上：

|路线 |目的|
|---|---|
| §鲁米§0§| Slack Events API 摄入 |
| §鲁米§0§| LINE Messaging API webhook 摄入 |
| §鲁米§0§|不和谐互动摄入量 |
| §鲁米§0§|不和谐消息事件接收 |
| §鲁米§0§|仅限秘密状态 |
| §鲁米§0§|设置或清除只写机密 |
| §鲁米§0§|类似 API 密钥的外部令牌状态 |
| §鲁米§0§|更新插入、重命名或删除命名外部令牌 |
| §鲁米§0§|列出内置和自定义输入/输出模板 |
| §鲁米§0§|注册自定义输入或输出模板 |
| §鲁米§0§|通用 webhook 摄入 |
| §鲁米§0§|列出 webhook 端点配置 |

## 本地主机输入端点

AI 创建的入站端点使用`input_endpoint_create`并且仅返回
本地主机 URL：

```text
http://localhost:{port}/api/webhooks/inbound/{endpoint_id}
```

这些端点需要共享密钥和默认 TTL 保护。公共
Cloudflare 或隧道 URL 仍然是一个单独的问题。
