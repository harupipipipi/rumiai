<!-- docs-i18n-links:start -->
[EN](../../webhooks.md) | [JP](../ja/webhooks.md) | [KR](../ko/webhooks.md) | [CN](./webhooks.md)
<!-- docs-i18n-links:end -->

# 网络钩子

Webhook 是外部输入框架的一种传输方式。 Webhook 处理程序
验证提供者请求，提取`ExternalEvent`，然后将
事件到策略和配置文件选择。 Webhook 代码应该保持精简。

## 处理程序形状

```text
HTTP request
  -> signature or token check
  -> provider parser
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> RumiInputEnvelope
  -> dispatch_input / submit_input
  -> ResponsePlanner
  -> ResponseAdapter
```

处理程序应该只执行特定于提供者的工作：

- 验证签名、时间戳或共享令牌；
- 回答提供商的质疑请求；
- 将有效负载字段映射到`ExternalEvent`；
- 返回提供者所需的确认格式；
- 调用所选的`ResponseAdapter`。

他们不应该决定模型行为、对话记忆策略、提示
选择，或代理路由。这些属于`InputProfile`。

## 请求验证

提供商验证必须在信任有效负载字段之前进行。

|供应商|验证|
|---|---|
|松弛| `x-slack-signature` 和 `x-slack-request-timestamp` |
|线路 | §鲁米§0§|
|不和谐 | `x-signature-ed25519` 和 `x-signature-timestamp` |
|通用 webhook |持有者令牌、HMAC 签名或其他配置的验证器 |

本地测试可能存在未签名的开发模式，但生产配置文件
必须要求验证。验证结果可以记录为布尔值或
状态字符串。原始签名秘密和入站令牌值绝不能
显示。

## 幂等性

每个 Webhook 事件都应该有一个稳定的 `event_id`。框架应该下降
重复使用：

```text
dedupe_key = provider + ":" + event_id
```

如果提供者不提供事件 ID，则处理程序可以从
时间戳加上消息 ID，或来自稳定有效负载字段的哈希值。不要散列
将原始秘密转化为 ID。

## 挑战和 Ack 响应

一些提供商在正常处理之前需要特殊响应：

- Slack `url_verification` 返回所提供的挑战。
- Discord ping 返回 ping 响应类型。
- LINE 通常接受普通的 HTTP 200 确认。

如果处理继续异步进行，则首先返回提供者 ack，然后让
`ResponseAdapter` 提供最终答复。

LINE `computer_use_line_biz` 端点可以选择快速确认行为
§鲁米§0§。这只会将 webhook 处理移至
进程内工作人员，以便提供者立即收到 HTTP 200；它没有
启用实验性后台桌面驱动程序。可见的计算机使用仍然存在
除非设置了`RUMI_ENABLE_EXPERIMENTAL_BACKGROUND_COMPUTER_USE=1`，否则为默认值。
那些 LINE Biz 计算机使用默认为当前聊天上下文如此古老
失败的工具日志和屏幕截图不会使下一个外部回复提示变得臃肿。

## 通用 Webhook 配置文件

通用 Webhook 应使用相同的外部输入路径：

```json
{
  "provider": "webhook",
  "event_id": "build_123",
  "kind": "event",
  "text": "Build failed on main",
  "metadata": {
    "repository": "example/repo",
    "status": "failed"
  }
}
```

配置文件决定这是否成为聊天消息、代理任务、流程
触发器或被忽略的事件。

Webhook 端点现在可以定义：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- `ttl_seconds`或`expires_at`

入站通用 Webhook 首先应用端点默认值，然后仅允许请求
明确列入白名单的交付覆盖。

## 公共 URL

Webhook 需要一个可访问的 URL，但 URL 提供程序位于框架之外。
Cloudflare Quick Tunnel 可能会提供临时开发 URL，但
运行时应将其视为可交换提供程序。必须使用相同的 webhook 合约
在本地主机、反向代理、平台路由或任何其他隧道后面工作。
