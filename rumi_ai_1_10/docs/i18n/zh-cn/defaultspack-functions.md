<!-- docs-i18n-links:start -->
[EN](../../defaultspack-functions.md) | [JP](../ja/defaultspack-functions.md) | [KR](../ko/defaultspack-functions.md) | [CN](./defaultspack-functions.md)
<!-- docs-i18n-links:end -->

# 默认包函数

Defaultspack 将其默认功能公开为 Rumi 函数。 HTTP 路由、AI 工具和 Flow 节点应将函数视为稳定的公共运行合约。

## 调用函数

当您知道时使用规范的限定名称：

```json
{
  "type": "function.call",
  "qualified_name": "defaultspack:ai_set_thinking_level",
  "args": {
    "scope": "profile",
    "profile_id": "openrouter/tencent/hy3-preview:free",
    "level": "high"
  }
}
```

函数还发布词汇别名，例如`defaults.ai.set_thinking_level`和`defaultspack.ai.set_thinking_level`。规范函数 id 从不包含点；别名可以。

## 函数与工具

函数是运行时/API 操作。工具只是人工智能模型的外观。

```json
{
  "tool_id": "set_thinking_level",
  "name": "set_thinking_level",
  "execution": {
    "type": "rumi_function",
    "qualified_name": "defaultspack:ai_set_thinking_level"
  }
}
```

`ToolExecutor` 通过共享的`CapabilityExecutor` 发送`rumi_function` 调用，因此工具使用和包间调用通过相同的权限边界。

## 思维水平

模型运行时设置归`ModelRuntimeSettingsService`所有。主要入口点是：

- `defaultspack:ai_get_preferred_model`
- `defaultspack:ai_set_preferred_model`
- `defaultspack:ai_get_thinking_level`
- `defaultspack:ai_set_thinking_level`
- `defaultspack:ai_get_effective_thinking_level`
- `defaultspack:ai_normalize_thinking_level`

当聊天或 AI 完成参数不包含`thinking_level`时，defaultspack 会从对话、个人资料和全局设置中解析服务器端的有效级别。

## 模型功能和路由

模型目录现在公开配置文件感知路由使用的功能元数据：

- `defaultspack:ai_search_models` / `defaults.ai.search_models`
- `defaultspack:ai_get_model_capabilities` / `defaults.ai.get_model_capabilities`
- `defaultspack:ai_recommend_model` / `defaults.ai.recommend_model`
- `defaultspack:ai_route_model` / `defaults.ai.route_model`
- `defaultspack:ai_explain_model_choice` / `defaults.ai.explain_model_choice`

能力字段包括`supports_vision`、`supports_tool_calling`、`supports_thinking`、`supports_fast`、`speed_tier`、`quality_tier`、`knowledge_level`、`knowledge_band`和角色建议。 `knowledge_level` 是相对的 rumiai 路由分数，而不是关于智能的绝对声明。

Vision Bridge 和兼容性实用程序路由可通过以下方式获得：

- `defaultspack:vision_describe_images` / `defaults.vision.describe_images`
- `defaultspack:agent_run_subagent` / `defaults.agent.run_subagent`（实用程序路由或委托运行的兼容性别名）
- `defaultspack:prompt_lint_prompt` / `defaults.prompt.lint_prompt`
- `defaultspack:prompt_compact_prompt` / `defaults.prompt.compact_prompt`

## 流程示例

```yaml
- id: set_reasoning
  phase: prepare
  priority: 10
  type: function
  function: defaultspack.ai.set_thinking_level
  input:
    scope: turn
    level: high
  output: thinking_level_result
```

## 安全

读取/列表/搜索/状态功能风险较低。改变聊天、人工智能调用、内存和工件通常是中等风险。文件写入、终端执行、git 推送/提交、提供程序密钥更改、浏览器/计算机控制、剪贴板写入和强制打包补丁操作属于高风险，并声明`caller_requires`。

包作者应通过`ToolExecutor`或共享`CapabilityExecutor`调用defaultspack函数，以便保留调用者主体。 `domain.function_runtime.bridge.invoke_function()` 默认为 HTTP 路由适配器和其他 defaultspack 拥有的后备的内部 `defaultspack` 主体；直接调用它的外部包必须传递显式的`principal_id`。
