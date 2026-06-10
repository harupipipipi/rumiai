<!-- docs-i18n-links:start -->
[EN](../../writing-prompts.md) | [JP](../ja/writing-prompts.md) | [KR](../ko/writing-prompts.md) | [CN](./writing-prompts.md)
<!-- docs-i18n-links:end -->

# 写作提示

使用默认包创建和管理提示模板的指南。处理程序在`blocks/prompt/`中实现，域逻辑在`domain/prompt/manager.py`（PromptManager）、`domain/prompt/template.py`（PromptTemplate）和`domain/prompt/renderer.py`（渲染）中实现。

## 提示概念

提示是一个包含模板变量的可重用文本模板。使用`{{variable_name}}`语法嵌入变量，并在渲染时将其替换为实际值。

提示由`PromptManager`（单例）管理，JSON 文件持久保存到内存中的 dict + `user_data/shared/prompts/`。启动时从 JSON 文件自动加载。

提示是一个被动层。必要时从流程/功能调用`defaults.prompt.render`或`defaults.prompt.resolve_for_conversation`，无需选择和执行工具/提供者/权限。

## 提示模板的格式

`PromptTemplate`类的结构在`domain/prompt/template.py`中定义。

```python
PromptTemplate(
    name="my_prompt",
    description="Prompt description",
    variables=[
        {"name": "user_name", "type": "string", "default": None, "required": True},
        {"name": "language", "type": "string", "default": "Japanese", "required": False},
    ],
    body="Hello, {{user_name}}! Please respond in {{language}}.",
    metadata={"author": "haru", "version": "1.0"},
)
```

持久化的 JSON 格式如下（`create_prompt()` of `domain/prompt/manager.py`）：

```json
{
  "id": "a1b2c3d4",
  "name": "my_prompt",
  "content": "Hello, {{user_name}}! Please respond in {{language}}.",
  "body": "Hello, {{user_name}}! Please respond in {{language}}.",
  "description": "プロンプトの説明",
  "variables": [
    {"name": "user_name", "type": "string", "default": null, "required": true},
    {"name": "language", "type": "string", "default": "Japanese", "required": false}
  ],
  "metadata": {"author": "haru", "version": "1.0"},
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

|领域 |类型 |描述 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ |自动生成 8 个字符的十六进制 ID |
| §鲁米§0§| §鲁米§1§ |提示名称（唯一）|
| §鲁米§0§| §鲁米§1§ |模板主体（`body`的别名。保留两者以实现向后兼容）|
| §鲁米§0§| §鲁米§1§ |模板主体|
| §鲁米§0§| §鲁米§1§ |说明|
| §鲁米§0§| §鲁米§1§ |变量定义列表|
| §鲁米§0§| §鲁米§1§ |自由格式元数据 |
| §鲁米§0§| §鲁米§1§ |创建日期和时间 (ISO 8601) |
| §鲁米§0§| §鲁米§1§ |更新日期和时间 (ISO 8601) |

变量的每个元素都有以下字段。

|领域 |类型 |描述 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ |变量名 |
| §鲁米§0§| §鲁米§1§ |类型（`"string"`、`"integer"`等）。默认`"string"` |
| §鲁米§0§| §鲁米§1§ |默认值。 `null` 无 |
| §鲁米§0§| §鲁米§1§ |是必须的吗？默认`false` |

旧格式 (`variables: ["var1", "var2"]`) 也受支持并自动转换为`_normalize_variables()` 中的新格式。

## 模板变量

### 常规变量

在`{{variable_name}}`中描述。在渲染期间替换为 `variables` 字典的值。 `domain/prompt/renderer.py`中的`render()`函数使用`_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")`一次性替换。

不存在的变量将被保留（并且不会导致错误）。允许使用空格（`{{ name }}` 也有效）。

### 特殊变量（上下文变量）

`CONTEXT_VARIABLE_KEYS` 在`domain/prompt/template.py`中定义。

|变量名 |类型 |描述 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ |当前上下文中的令牌总数 |
| §鲁米§0§| §鲁米§1§ |消息数量 |
| §鲁米§0§| §鲁米§1§ |留言内容。对于list/dict，转换为JSON字符串 |
| §鲁米§0§| §鲁米§1§ |系统提示|
| §鲁米§0§| §鲁米§1§ |对话 ID |

特殊变量通过`PromptManager.inject_context_variables(variables, context)`自动注入。用户明确指定的值不会被覆盖。该值是从上下文字典中的相应键（`total_tokens`、`message_count`等）中检索的。

###变量提取方法

`PromptTemplate`类提供了分析体内变量的方法。

```python
template = PromptTemplate(body="Hello {{name}}, tokens: {{context.total_tokens}}")
template.extract_variable_names()   # → ["name", "context.total_tokens"]
template.list_user_variables()      # → ["name"]
template.list_context_variables()   # → ["context.total_tokens"]
```

## 通过 API 进行增删改查

### 创建提示

**处理程序**：`defaults.prompt.create`（`blocks/prompt/create.py`）

HTTP 传输没有直接的提示创建路由。通过`call_handler`致电。

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "my_prompt",
    "content": "Hello, {{user_name}}!",
    "variables": [{"name": "user_name", "type": "string", "required": True}]
})
```

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |提示名称 |
| §鲁米§0§| §鲁米§1§ |是的 |模板主体|
| §鲁米§0§| §鲁米§1§ |没有 |变量定义。 `["var1"]` 格式（旧）和`[{"name": "var1", ...}]` 格式（新）均可 |

**返回值**：`ok({"prompt": {...}})`

### 提示列表

**处理程序**：`defaults.prompt.list`（`blocks/prompt/list.py`）

HTTP 传输没有直接的提示列表路由。通过`call_handler`致电。

```python
result = context["call_handler"]("defaults.prompt.list", {})
```

**输入数据**：`{}`（无参数）

**返回值**：`ok({"prompts": [...]})`

### 及时更新

**处理程序**：`defaults.prompt.update`（`blocks/prompt/update.py`）

**HTTP**：`PUT /api/prompts/{name}`

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |提示名称要更新（从URL路径自动注入）|
| §鲁米§0§| §鲁米§1§ |是的 |要更新的字段 |

`updates` 的可能字段：`content`（或`body`）、`description`、`variables`、`metadata`、`name`（重命名）。重命名时，旧文件将被删除，索引将自动更新。

**返回值**：`ok({"prompt": {...}})`

### 删除提示

**处理程序**：`defaults.prompt.delete`（`blocks/prompt/delete.py`）

**HTTP**：`DELETE /api/prompts/{name}`

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |提示名称（从 URL 路径自动注入）|

**返回值**：`ok({"deleted": "prompt_name"})`

### 提示渲染

**处理程序**：`defaults.prompt.render`（`blocks/prompt/render.py`）

HTTP 传输没有直接的渲染路由。通过`call_handler`致电。

```python
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "a1b2c3d4",
    "variables": {"user_name": "Haru"}
})
```

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |没有 |提示ID。指定后，从 PromptManager | 检索
| §鲁米§0§| §鲁米§1§ |没有 |直接指定模板字符串。 `prompt_id` 优先 |
| §鲁米§0§| §鲁米§1§ |没有 |变量值 |

**返回值**：`ok({"rendered": "rendered string", "prompt_id": "..." or null})`

###系统提示

**处理程序**：`defaults.prompt.system`（`blocks/prompt/system.py`）

获得：`{"action": "get"}`→`ok({"content": "..."})`

设置：`{"action": "set", "content": "new system prompt"}`→`ok({"content": "..."})`

###工具↔提示转换

**处理程序**：`defaults.prompt.convert`（`blocks/prompt/convert.py`）

**HTTP**：`POST /api/prompts/convert`

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 | `"tool"` 或 `"prompt"` |
| §鲁米§0§| §鲁米§1§ |是的 |来源名称 |
| §鲁米§0§| §鲁米§1§ |是的 | `"tool"` 或 `"prompt"`（必须与 source_type 不同）|

**工具 → 提示**：将工具的`parameters`转换为变量，将`summary`转换为模板主体标题。使用`PromptTemplate.from_tool_schema()`。

**提示→工具**：作为创作路线无效。 `execution.type: "prompt"`工具将不会被创建。如有必要，请从流程/函数调用`defaults.prompt.render`，如果您需要工具，请将其单独定义为`rumi_function`或`capability`外观。

## 获取上下文的示例

```python
# プロンプトを作成（call_handler 経由）
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_aware",
    "content": "Messages so far: {{context.message_count}}\nConversation: {{context.conversation_id}}\n\nUser request: {{request}}",
    "variables": [{"name": "request", "type": "string", "required": True}]
})
```

当您在渲染时传递上下文时，`inject_context_variables()`将自动注入`context.message_count`和`context.conversation_id`。

## 具体例子

### 示例 1：代码审查提示

```python
# call_handler 経由でプロンプトを作成
result = context["call_handler"]("defaults.prompt.create", {
    "name": "code_review",
    "content": "Please review the following {{language}} code:\n\n```{{language}}\n{{code}}\n```\n\nFocus on: {{focus_areas}}\nSeverity threshold: {{severity}}",
    "variables": [
        {"name": "language", "type": "string", "required": True},
        {"name": "code", "type": "string", "required": True},
        {"name": "focus_areas", "type": "string", "default": "bugs, performance, readability"},
        {"name": "severity", "type": "string", "default": "medium"}
    ]
})
```

### 示例2：翻译提示

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "translator",
    "content": "Translate the following text from {{source_lang}} to {{target_lang}}.\n\nStyle: {{style}}\n\nText:\n{{text}}",
    "variables": [
        {"name": "source_lang", "type": "string", "required": True},
        {"name": "target_lang", "type": "string", "required": True},
        {"name": "text", "type": "string", "required": True},
        {"name": "style", "type": "string", "default": "natural"}
    ]
})
```

### 示例 3：上下文感知摘要提示

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_summary",
    "content": "Conversation has {{context.message_count}} messages ({{context.total_tokens}} tokens).\n\nPlease summarize the conversation so far, focusing on: {{focus}}\n\nMessages:\n{{context.messages}}",
    "variables": [
        {"name": "focus", "type": "string", "default": "key decisions and action items"}
    ]
})
```

## 最佳实践

`name` 应该是一个清楚描述提示目的的名称。这使得在提示列表中更容易识别它们。

请在`variables`中适当设置`required: true`。如果未指定所需变量，`{{variable_name}}` 仍保留在输出中。

使用`{{context.*}}`变量在运行时自动将上下文信息注入`content`（主体）中。如果用户显式指定一个值，则不会被覆盖，因此测试时可以传递模拟值。

根据提示自动生成工具的创作路径无效。 `context.*`变量由`defaults.prompt.resolve_for_conversation`被动解析，并且如果需要工具，则单独定义为`rumi_function`/`capability`外观。

持久性文件 (`user_data/shared/prompts/`) 由`PromptManager` 管理。文件名由`_safe_filename(name) + ".json"`生成，字母数字字符、连字符和下划线以外的字符将转换为下划线。
