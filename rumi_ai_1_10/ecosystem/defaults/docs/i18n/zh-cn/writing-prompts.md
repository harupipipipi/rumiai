<!-- docs-i18n-links:start -->
[EN](../../writing-prompts.md) | [JP](../ja/writing-prompts.md) | [KR](../ko/writing-prompts.md) | [CN](./writing-prompts.md)
<!-- docs-i18n-links:end -->

# 写作提示

使用默认包创建和管理提示模板的指南。处理程序在 `blocks/prompt/` 中实现，域逻辑在 `domain/prompt/manager.py` (PromptManager)、`domain/prompt/template.py` (PromptTemplate) 和 `domain/prompt/renderer.py` (render) 中实现。

## 提示概念

提示是一个包含模板变量的可重用文本模板。使用`{{variable_name}}`语法嵌入变量，并在渲染时将其替换为实际值。

提示由 `PromptManager`（单例）管理，JSON 文件持久保存到内存中的 dict + `user_data/shared/prompts/`。启动时从 JSON 文件自动加载。

提示和工具可通过`PromptTemplate`互换。 `blocks/prompt/convert.py`允许您转换工具→提示、提示→工具。

## 提示模板的格式

`domain/prompt/template.py`中定义的`PromptTemplate`类的结构。

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

持久化的 JSON 格式如下（第 `domain/prompt/manager.py` 的`create_prompt()`）：

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

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Automatically generated 8-character hex ID |
| `name` | `string` | Prompt name (unique) |
| `content` | `string` | Template body (alias of `body`. Keep both for backwards compatibility) |
| `body` | `string` | Template body |
| `description` | `string` | Explanation |
| `variables` | `list[dict]` | Variable definition list |
| `metadata` | `dict` | Free-form metadata |
| `created_at` | `string` | Creation date and time (ISO 8601) |
| `updated_at` | `string` | Updated date and time (ISO 8601) |

变量的每个元素都有以下字段。

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Variable name |
| `type` | `string` | type (`"string"`, `"integer"`, etc.). Default `"string"` |
| `default` | `any` | Default value. None for `null` |
| `required` | `bool` | Is it required? Default `false` |

旧格式 (`variables: ["var1", "var2"]`) 也受支持并自动转换为`_normalize_variables()`中的新格式。

## 模板变量

### 常规变量

`{{variable_name}}`中描述。在渲染期间替换为 `variables` dict 的值。 `domain/prompt/renderer.py`中的`render()`函数使用`_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")`一次性替换。

不存在的变量将被保留（并且不会导致错误）。允许使用空格（`{{ name }}` 也有效）。

### 特殊变量（上下文变量）

`CONTEXT_VARIABLE_KEYS`在`domain/prompt/template.py`中定义。

| Variable name | Type | Description |
|---|---|---|
| `{{context.total_tokens}}` | `int` | Total number of tokens in current context |
| `{{context.message_count}}` | `int` | Number of messages |
| `{{context.messages}}` | `string/list` | Message content. For list/dict, it is converted to JSON string |
| `{{context.system_prompt}}` | `string` | System prompt |
| `{{context.conversation_id}}` | `string` | Conversation ID |

特殊变量通过 `PromptManager.inject_context_variables(variables, context)` 自动注入。用户明确指定的值不会被覆盖。该值是从上下文字典中的相应键检索的（`total_tokens`、`message_count`等）。

### 变量提取方法

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

HTTP 传输没有直接的提示创建路由。通过 `call_handler` 致电。

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "my_prompt",
    "content": "Hello, {{user_name}}!",
    "variables": [{"name": "user_name", "type": "string", "required": True}]
})
```

**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name |
| `content` | `string` | Yes | Template body |
| `variables` | `list` | No | Variable definition. Both `["var1"]` format (old) and `[{"name": "var1", ...}]` format (new) are possible |

**返回值**：`ok({"prompt": {...}})`

### 提示列表

**处理程序**：`defaults.prompt.list`（`blocks/prompt/list.py`）

HTTP 传输没有直接的提示列表路由。通过 `call_handler` 致电。

```python
result = context["call_handler"]("defaults.prompt.list", {})
```

**输入数据**：`{}`（无参数）**返回值**：`ok({"prompts": [...]})`

### 及时更新

**处理程序**：`defaults.prompt.update`（`blocks/prompt/update.py`）**HTTP**：`PUT /api/prompts/{name}`**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name to be updated (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update |

`updates` 的可能字段：`content`（或`body`）、`description`、`variables`、`metadata`、`name`（重命名）。重命名时，旧文件将被删除，索引将自动更新。

**返回值**：`ok({"prompt": {...}})`

### 删除提示

**处理程序**：`defaults.prompt.delete`（`blocks/prompt/delete.py`）**HTTP**：`DELETE /api/prompts/{name}`**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name (auto-injected from URL path) |

**返回值**：`ok({"deleted": "prompt_name"})`

### 提示渲染

**处理程序**：`defaults.prompt.render`（`blocks/prompt/render.py`）

HTTP 传输没有直接的渲染路由。通过 `call_handler` 致电。

```python
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "a1b2c3d4",
    "variables": {"user_name": "Haru"}
})
```

**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt_id` | `string` | No | Prompt ID. When specified, retrieved from PromptManager |
| `template` | `string` | No | Specify template string directly. `prompt_id` takes precedence |
| `variables` | `dict` | No | Variable value |

**返回值**：`ok({"rendered": "rendered string", "prompt_id": "..." or null})`

### 系统提示

**处理程序**：`defaults.prompt.system`（`blocks/prompt/system.py`）

获得：`{"action": "get"}`→`ok({"content": "..."})`

设置：`{"action": "set", "content": "new system prompt"}`→`ok({"content": "..."})`

### 工具↔提示转换

**处理程序**：`defaults.prompt.convert`（`blocks/prompt/convert.py`）**HTTP**：`POST /api/prompts/convert`**输入数据**：

| Field | Type | Required | Description |
|---|---|---|---|
| `source_type` | `string` | Yes | `"tool"` or `"prompt"` |
| `source_name` | `string` | Yes | Source name |
| `target_type` | `string` | Yes | `"tool"` or `"prompt"` (must be different from source_type) |

**工具→提示**：将工具的`parameters`转换为变量，将`summary`转换为模板主体标题。使用`PromptTemplate.from_tool_schema()`。**提示→工具**：将模板变量转换为`parameters`，将正文转换为`execution.body`。 `PromptTemplate.to_tool_schema()`在`ToolRegistry.register_dynamic()`中作为`execution.type: "prompt"`中的工具使用和注册。 context.* 变量从工具参数中排除。

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

请在`variables`中适当设置`required: true`。如果未指定所需变量，则 `{{variable_name}}` 保留在输出中。

使用 `{{context.*}}` 变量在运行时自动将上下文信息注入到 `content`（主体）中。如果用户显式指定一个值，则不会被覆盖，因此测试时可以传递模拟值。

在提示到工具转换 (`prompt → tool`) 中，`context.*` 变量会自动从工具参数中排除。这是因为上下文变量预计会在运行时自动注入。

持久性文件 (`user_data/shared/prompts/`) 由`PromptManager` 管理。文件名由`_safe_filename(name) + ".json"`生成，字母数字字符、连字符和下划线以外的字符将转换为下划线。
