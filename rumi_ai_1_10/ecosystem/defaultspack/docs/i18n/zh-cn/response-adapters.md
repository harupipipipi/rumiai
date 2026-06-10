<!-- docs-i18n-links:start -->
[EN](../../response-adapters.md) | [JP](../ja/response-adapters.md) | [KR](../ko/response-adapters.md) | [CN](./response-adapters.md)
<!-- docs-i18n-links:end -->

# 响应适配器

响应适配器将 Rumi 输出转换为特定于提供者的回复。他们是
外部输入框架的出站部分。

```text
runtime result
  -> ResponsePromptPolicy
  -> ResponsePlanner
  -> ResponsePlan
  -> ResponseAdapter
  -> provider API or HTTP response
```

运行时不应该知道如何发布到 Slack、使用 LINE 回复令牌，或者
格式化 Discord 交互响应。它应该返回一个提供者中立的
计划者可以适应的结果。

## 响应计划器

`ResponsePlanner` 决定运行时结果应该发生什么：

- `reply_text`：将助手文本发送回源；
- `store_only`：保留聊天结果，无需外部回复；
- `summarize_then_reply`：发送简短的有限摘要；
- `run_browser_use`、`run_computer_use`、`run_python`、`run_tool`：创建
  后续行动计划，而非直接执行；
- `send_file_if_allowed`：允许在能力检查后进行正常的文件规划；
- `ask_for_approval`：停止在需要批准的计划上。

策划者阅读即时决定、提供商限制、活动受众和
运行时输出元数据。提供程序长度限制、文件限制和敏感度
迅速做出决定后仍会进行检查。

输出配置文件是输入配置文件的出站对应项。内置
配置文件涵盖 LINE 回复/推送、Discord 机器人频道消息、Discord webhook
URL、Slack 通道/线程消息、通用 Webhook 回调和本地 Web
输出。自定义配置文件可以放置在`user_data/shared/output_profiles`中。
对于内置 LINE/Discord/Slack 输出，设置是有意复制粘贴的
选择：选择输出模板/配置文件，将非秘密目标 ID 粘贴到
UI，并将机器人令牌或 Webhook URL 存储为屏蔽的外部令牌。任意
发件人和自由格式的提示说明位于“自定义”下。

Discord 公开了两个内置输出模板，因为操作模型是
不同：

- `discord.output.bot_channel`：本地 Rumi 运行时使用 Discord Bot 令牌
  和目标`channel_id`。
- `discord.output.webhook`：Rumi 通过频道 Webhook URL 发布内容并执行
  该输出路径不需要机器人令牌。

两条路径仍然经过响应计划并保证`allowed_mentions`的安全
默认情况下。

## 响应提示策略

`response_prompt` 是一项快速路线规划政策。它可能会检查事件，
输入文本和运行时结果，然后返回`plan_only`决策
`ResponsePlanner`，但不得直接执行工具或调用提供者 API。
稍后通过现有工具策略创建可执行步骤，
批准、回合运行和响应适配器路径。

策略字段在`schemas/response_prompt_policy.schema.yaml`中定义：

- `allowed_actions`：提示可能的唯一`ResponsePlan.action`值
  返回；
- `tools`：规划环境的工具可见性和批准要求；
- `output_schema`：即时决策的预期结构形式；
- `allowed_outputs`：可选的输出配置文件 ID 或提示可能提供的提供者
  目标；
- `fallback`：提示输出无效时使用的安全操作或
  被拒绝；
- `sensitivity`：可见性默认值和外部交付限制。

任何未在`allowed_actions`中列出的决定都必须被拒绝
并通过`fallback`处理。

示例：

```yaml
response_prompt:
  enabled: true
  model: inherit
  mode: plan_only
  allowed_actions:
    - reply_text
    - store_only
    - run_browser_use
    - run_python
  tools:
    browser_use:
      enabled: true
      requires_approval: false
    python:
      enabled: true
      requires_approval: false
      sandbox: true
    external_send:
      enabled: true
      requires_approval: true
  system_prompt: |
    Decide how Rumi should respond. Use browser_use only when current
    external information is needed. Return strict JSON.
  user_prompt: |
    Provider: ${event.provider}
    Scope: ${event.scope.type}:${event.scope.id}
    Actor: ${event.actor.id}
    User input: ${input.text}
    Assistant result: ${response.text}
```

对于跨提供商操作，提示应返回一个计划，例如
`run_tool` 与`tool: external_send`。该工具经过批准并使用
与正常响应相同的 LINE、Discord、Slack 和通用 Webhook 适配器
交货。提示永远不会收到原始机器人令牌或 Webhook 机密。

## 响应计划

计划示例：

```json
{
  "provider": "discord",
  "messages": [
    {
      "type": "text",
      "text": "Here is the summary..."
    }
  ],
  "metadata": {
    "response_prompt_decision": {
      "action": "reply_text",
      "sensitivity": "public"
    },
    "response_action_plan": {
      "type": "reply",
      "external_reply": true
    }
  }
}
```

目标可能包含提供者标识符，但不包含原始授权值。任意
短期回复句柄应作为内部参考传递并解决
适配器内部。

## 适配器职责

`ResponseAdapter` 负责：

- 呈现提供商特定的消息形状；
- 执行提供商长度限制；
- 除非政策允许，否则避免大量提及；
- 拒绝主动响应提示政策之外的行为；
- 在外部答复之前重新检查敏感性和能力；
- 解决来自秘密存储的秘密引用；
- 调用提供商API；
- 返回经过编辑的交付状态；
- 将提供者错误映射到稳定框架错误。

适配器可以是同步的或异步的。如果提供商需要快速的 HTTP 响应，
Webhook 处理程序可以在适配器稍后发送时返回 ack。

## 内置适配器目标

|适配器|交付目标|
|---|---|
| §鲁米§0§| Slack `chat.postMessage` 与可选的`thread_ts` |
| §鲁米§0§|使用短期回复令牌的 LINE 回复 API 参考 |
| §鲁米§0§| Discord 交互响应体 |
| §鲁米§0§| Discord 频道消息 API |
| §鲁米§0§| Discord Webhook URL |
| §鲁米§0§|通用 JSON 响应或回调 URL |
| §鲁米§0§|工具支持的 LINE/Discord/Slack/通用 批准后发送 |

适配器 ID 由`InputProfile` 选择，而不是由聊天处理程序选择。

## 错误行为

仅当配置文件允许时，公共频道才应接收安全、简短的错误
那种行为。详细的提供商错误属于经过编辑的日志或交付
状态，不在频道回复中。

示例：

|状况 |建议行动 |
|---|---|
|缺少出站令牌 |未经原始秘密的编辑传递错误 |
|提供商速率限制 | `store_only` 或提供商特定的延迟处理 |
|留言太长 |正常计划者分块|
|规划后保单被拒绝| §鲁米§0§|

## 安全规则

响应提示策略在操作边界处默认拒绝：

- 默认情况下，`computer_use` 需要明确批准，即使它在
规划背景。
- `allowed_actions` 之外的计划在适配器交付之前被拒绝。
- `browser_use` 必须遵守主动网络政策。
- `python`后续计划必须声明沙箱/仅限本地的期望。
- 在任何外部回复之前，适配器路径会重新检查`sensitivity`和当前
  功能，因此过时的提示输出不会泄漏仅限本地或秘密内容。
