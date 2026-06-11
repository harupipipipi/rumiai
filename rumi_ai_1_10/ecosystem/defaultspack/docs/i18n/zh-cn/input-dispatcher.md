<!-- docs-i18n-links:start -->
[EN](../../input-dispatcher.md) | [JP](../ja/input-dispatcher.md) | [KR](../ko/input-dispatcher.md) | [CN](./input-dispatcher.md)
<!-- docs-i18n-links:end -->

# 输入调度程序

`submit_input` 仍然是公共兼容性入口点，但规范
现在的路径是：

```text
RumiInputEnvelope
  -> dispatch_input
  -> action_registry
  -> delivery.action_id handler
```

## 信封形状

每个入站转弯都被标准化为`RumiInputEnvelope`。

- `source`：谁或什么产生了输入
- `target`：对话、路线或运行时目标
- `delivery`：动作选择元数据
- `input`：主要文本负载
- `params`：特定于操作的结构化数据
- `tools`：可选的显式工具选择
- `attachments`：回合中携带的文件或图像
- `metadata`：审计和提供商元数据

`delivery.action_id` 默认为`chat.message`。

## 内置动作

- `chat.message`：正常用户消息流
- `run.instruction`：将运行时引导/指令排入队列
- `run.interrupt`：紧急运行时指令，为未来的暂停/取消/重定向语义留出空间
- `agent.delegate`：从结构化有效负载启动一个委托代理运行
- `model.switch`：保留对话默认模型更改
- `model.route`：设置转弯范围的路线覆盖

未知的`delivery.action_id`值返回结构化错误而不是
落入特定于提供者的逻辑。

## 兼容性

- 现有的`submit_input(...)`呼叫者仍然可以工作。
- 现有的聊天发送行为仍然通过相同的商店和街区进行路由。
- 旧版 `subagent` 命名的呼叫站点现在使用 `agent.delegate` 或
`model.call`风格的内部实用路由。
