<!-- docs-i18n-links:start -->
[EN](../../input-profiles.md) | [JP](../ja/input-profiles.md) | [KR](../ko/input-profiles.md) | [CN](./input-profiles.md)
<!-- docs-i18n-links:end -->

# 输入配置文件

`InputProfile`描述了允许的`ExternalEvent`如何成为运行时输入。
它是外部受众背景和鲁米行为之间的桥梁。

配置文件使提供商边缘代码保持较小。 Webhook 处理程序规范事件；
配置文件选择鲁米应该如何处理这些事件。

## 职责

输入配置文件选择：

- 目的地类型：聊天、代理、流或忽略；
- 对话关键策略；
- 模型和提示默认值；
- 内存和上下文策略；
- 响应适配器；
- 允许的事件类型；
- 文本转换和附件处理；
- 当事件无法得到响应时的后备行为。

配置文件不存储原始秘密值。他们可能会提到秘密名字或
凭证 ID。

## 示例

```json
{
  "id": "slack-support-thread",
  "enabled": true,
  "provider": "slack",
  "match": {
    "team_id": "T123",
    "channel_id": "C_SUPPORT",
    "event_kinds": ["message", "app_mention"]
  },
  "audience_policy_id": "support-channel-policy",
  "destination": {
    "type": "chat",
    "conversation_kind": "external",
    "session_key": "slack:{team_id}:{channel_id}:{thread_id}"
  },
  "runtime": {
    "model": "stub/default",
    "system_prompt_id": "support_assistant"
  },
  "response": {
    "adapter_id": "slack-thread",
    "mode": "reply"
  }
}
```

## 观众政策链接

`AudiencePolicy`回答“这个事件可以进入鲁米吗？”。
`InputProfile`回答“鲁米应该用它做什么？”。

配置文件应该引用策略而不是嵌入广泛的允许规则。
这使得审核、速率限制和观众门可在多个
配置文件。

## 会话密钥

配置文件应生成稳定的会话密钥，以便外部对话映射回来
现有的鲁米对话：

|供应商|会话密钥示例 |
|---|---|
|松弛的螺纹 | §鲁米§0§|
|松弛DM | §鲁米§0§|
|线源 | §鲁米§0§|
|不和谐频道 | §鲁米§0§|
|通用 webhook | §鲁米§0§|

会话密钥不是凭证。如果不包含秘密，则可以记录
或敏感消息内容。

## 提交输入负载

`submit_input` 应接收标准化事件和选定的配置文件：

```json
{
  "event": {
    "event_id": "evt_01",
    "provider": "slack",
    "text": "summarize the thread"
  },
  "profile": {
    "id": "slack-support-thread",
    "destination": {"type": "chat"}
  },
  "policy": {
    "decision": "allow"
  }
}
```

该函数返回与提供者无关的运行时结果。提供商交付是
稍后由`ResponsePlanner`和`ResponseAdapter`处理。

## 配置文件安全默认值

- 默认为禁用，直到明确启用为止；
- 需要经过验证的事件，除非本地开发标志处于活动状态；
- 默认忽略机器人/自我消息；
- 使用最小权限模型、工具和代理设置；
- 宁愿不回应也不愿做出不安全的公众回应；
- 在审核或 UI 显示之前编辑元数据。
