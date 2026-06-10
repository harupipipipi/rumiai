<!-- docs-i18n-links:start -->
[EN](../../dev-tools.md) | [JP](../ja/dev-tools.md) | [KR](../ko/dev-tools.md) | [CN](./dev-tools.md)
<!-- docs-i18n-links:end -->

# 开发工具指南

## 1. 概念

开发工具是默认为开发人员提供的一组检查和调试功能。提供AI请求详细信息、提示使用历史记录、实时编辑和请求重放。

开发工具处理程序放置在`blocks/dev/`目录中，并声明为`ecosystem.json`的`dev`组件。特定的 UI 面板作为 user_data 端的资产提供，但默认包包含`ui/dev_panel.js`中的参考实现。

`blocks/dev/` 包含以下文件。

|文件|处理者名称 |
|---|---|
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |


## 2.检查（确认请求信息）

查看提交给 LLM 的请求的完整详细信息。

**处理程序**：`defaults.dev.inspect`（`blocks/dev/inspect.py`）

**HTTP**：`GET /api/dev/inspect`

```python
# handler 経由で直前のリクエスト情報を取得
info = context["call_handler"]("defaults.dev.inspect", {
    "conversation_id": "conv-1",
    "message_id": "msg-latest"
})
```

返回值：
```json
{
  "request": {
    "model": "claude-sonnet-4-20250514",
    "provider": "anthropic",
    "messages": [ "...StandardMessage 配列..." ],
    "tools": [ "...ツール定義..." ],
    "params": { "temperature": 0.7, "max_tokens": 8192 },
    "system_prompt": "...レンダリング済みシステムプロンプト...",
    "total_input_tokens": 12500
  },
  "response": {
    "content": [ "...Content Block 配列..." ],
    "finish_reason": "tool_calls",
    "usage": { "input_tokens": 12500, "output_tokens": 350 },
    "latency_ms": 2800,
    "time_to_first_token_ms": 650
  },
  "context_breakdown": {
    "system_prompt_tokens": 1500,
    "project_memory_tokens": 800,
    "user_memory_tokens": 200,
    "tools_tokens": 3000,
    "history_tokens": 7000,
    "reserve_tokens": 0
  }
}
```


## 3.提示历史记录

查看会话期间呈现的提示的历史记录。

**处理程序**：`defaults.dev.prompt_history`（`blocks/dev/prompt_history.py`）

**HTTP**：`GET /api/dev/prompt-history`

```python
history = context["call_handler"]("defaults.dev.prompt_history", {
    "session_id": "sess-123",
    "limit": 20
})
```

返回值：
```json
[
  {
    "timestamp": 1771056800000,
    "prompt_id": "coding_system",
    "variables_used": ["agent_name", "tools", "project_memory"],
    "rendered_length": 3200,
    "source": "user_data/shared/prompts/coding_system"
  }
]
```


## 4.实时编辑提示

即时编辑和覆盖提示。如果指定的`prompt_name`提示存在，则更新`content`；如果不存在，则创建一个新的。为`prompt_name` 指定`"system"` 会重写系统提示符。

**处理程序**：`defaults.dev.edit_prompt_live`（`blocks/dev/edit_prompt_live.py`）

**HTTP**：`POST /api/dev/edit-prompt`

```python
context["call_handler"]("defaults.dev.edit_prompt_live", {
    "prompt_name": "coding_system",
    "new_body": "あなたは関数型プログラミングの専門家です。..."
})
```

返回值：
```json
{
  "status": "ok",
  "data": {
    "prompt_name": "coding_system",
    "updated": true,
    "content": "あなたは関数型プログラミングの専門家です。...",
    "prompt_id": "a1b2c3d4"
  }
}
```

要恢复，请在`new_body`中指定原始模板主体并再次调用它。


## 5.重放（重放过去的请求）

使用相同的参数重新运行之前的 LLM 请求。也可以更改模型和参数。

**处理程序**：`defaults.dev.replay`（`blocks/dev/replay.py`）

**HTTP**：`POST /api/dev/replay`

```python
result = context["call_handler"]("defaults.dev.replay", {
    "conversation_id": "conv-1",
    "message_id": "msg-005",
    "override": {
        "model": "openai/gpt-4o",
        "params": {"temperature": 0.0}
    }
})
```

返回值的格式与`defaults.ai.complete`相同。重用原始请求中的消息数组和工具定义，仅替换模型和参数，然后重新运行。


## 6. 使用 Ctrl+Shift+D 显示面板

前端的资源检测`Ctrl+Shift+D`键绑定并切换开发工具面板的显示/隐藏。

面板资产以用户数据包的形式提供。 defaults 提供开发工具处理程序（`defaults.dev.inspect`、`defaults.dev.prompt_history`、`defaults.dev.edit_prompt_live`、`defaults.dev.replay`）。参考实现包含在默认包的`ui/dev_panel.js`中。

建议将`panel.bottom`或`floating`用于面板资产放置槽。


## 7. API 端点

|处理程序 | HTTP 路由 |输入数据|返回值|
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |请求/响应详细信息 |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |提示使用历史数组 |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ | §鲁米§3§|
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |标准响应 |
