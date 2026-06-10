<!-- docs-i18n-links:start -->
[EN](./writing-prompts.md) | [JP](./i18n/ja/writing-prompts.md) | [KR](./i18n/ko/writing-prompts.md) | [CN](./i18n/zh-cn/writing-prompts.md)
<!-- docs-i18n-links:end -->

# Writing Prompts

A guide for creating and managing prompt templates with defaults pack. The handler is implemented in `blocks/prompt/`, and the domain logic is implemented in `domain/prompt/manager.py` (PromptManager), `domain/prompt/template.py` (PromptTemplate), and `domain/prompt/renderer.py` (render).

## prompt concept

prompt is a reusable text template containing template variables. Embed variables with the `{{variable_name}}` syntax and replace them with actual values ​​when rendering.

Prompts are managed by `PromptManager` (singleton) with JSON file persistence to in-memory dict + `user_data/shared/prompts/`. Autoloaded from a JSON file on startup.

The prompt is a passive layer. Call `defaults.prompt.render` or `defaults.prompt.resolve_for_conversation` from flow/function when necessary without selecting and executing tool/provider/permission.

## Format of PromptTemplate

Structure of the `PromptTemplate` class defined in `domain/prompt/template.py`.

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

The persisted JSON format is as follows (`create_prompt()` of `domain/prompt/manager.py`):

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

Each element of variables has the following fields.

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Variable name |
| `type` | `string` | type (`"string"`, `"integer"`, etc.). Default `"string"` |
| `default` | `any` | Default value. None for `null` |
| `required` | `bool` | Is it required? Default `false` |

The old format (`variables: ["var1", "var2"]`) is also supported and automatically converted to the new format in `_normalize_variables()`.

## Template variables

### Regular variables

Described in `{{variable_name}}`. Replaced with the value of `variables` dict during rendering. The `render()` function in `domain/prompt/renderer.py` uses `_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")` to replace in one pass.

Variables that do not exist are left alone (and do not result in an error). Spaces are allowed (`{{ name }}` is also valid).

### Special variables (context variables)

`CONTEXT_VARIABLE_KEYS` defined in `domain/prompt/template.py`.

| Variable name | Type | Description |
|---|---|---|
| `{{context.total_tokens}}` | `int` | Total number of tokens in current context |
| `{{context.message_count}}` | `int` | Number of messages |
| `{{context.messages}}` | `string/list` | Message content. For list/dict, it is converted to JSON string |
| `{{context.system_prompt}}` | `string` | System prompt |
| `{{context.conversation_id}}` | `string` | Conversation ID |

Special variables are auto-injected with `PromptManager.inject_context_variables(variables, context)`. Values ​​explicitly specified by the user are not overwritten. The value is retrieved from the corresponding key in the context dict (`total_tokens`, `message_count`, etc.).

### Variable extraction method

The `PromptTemplate` class provides methods to analyze variables within body.

```python
template = PromptTemplate(body="Hello {{name}}, tokens: {{context.total_tokens}}")
template.extract_variable_names()   # → ["name", "context.total_tokens"]
template.list_user_variables()      # → ["name"]
template.list_context_variables()   # → ["context.total_tokens"]
```

## CRUD via API

### Create prompt

**handler**: `defaults.prompt.create`（`blocks/prompt/create.py`）

There is no direct prompt creation route for the HTTP transport. Call via `call_handler`.

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "my_prompt",
    "content": "Hello, {{user_name}}!",
    "variables": [{"name": "user_name", "type": "string", "required": True}]
})
```

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name |
| `content` | `string` | Yes | Template body |
| `variables` | `list` | No | Variable definition. Both `["var1"]` format (old) and `[{"name": "var1", ...}]` format (new) are possible |

**Return value**: `ok({"prompt": {...}})`

### List of prompts

**handler**: `defaults.prompt.list`（`blocks/prompt/list.py`）

There is no direct prompt list route for the HTTP transport. Call via `call_handler`.

```python
result = context["call_handler"]("defaults.prompt.list", {})
```

**input_data**: `{}` (no parameters)

**Return value**: `ok({"prompts": [...]})`

### Prompt update

**handler**: `defaults.prompt.update`（`blocks/prompt/update.py`）

**HTTP**: `PUT /api/prompts/{name}`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name to be updated (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update |

Possible fields for `updates`: `content` (or `body`), `description`, `variables`, `metadata`, `name` (rename). When renaming, old files will be deleted and the index will be updated automatically.

**Return value**: `ok({"prompt": {...}})`

### Delete prompt

**handler**: `defaults.prompt.delete`（`blocks/prompt/delete.py`）

**HTTP**: `DELETE /api/prompts/{name}`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name (auto-injected from URL path) |

**Return value**: `ok({"deleted": "prompt_name"})`

### Prompt rendering

**handler**: `defaults.prompt.render`（`blocks/prompt/render.py`）

There is no direct rendering route for HTTP transport. Call via `call_handler`.

```python
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "a1b2c3d4",
    "variables": {"user_name": "Haru"}
})
```

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt_id` | `string` | No | Prompt ID. When specified, retrieved from PromptManager |
| `template` | `string` | No | Specify template string directly. `prompt_id` takes precedence |
| `variables` | `dict` | No | Variable value |

**Return value**: `ok({"rendered": "rendered string", "prompt_id": "..." or null})`

### System prompt

**handler**: `defaults.prompt.system`（`blocks/prompt/system.py`）

Obtain: `{"action": "get"}` → `ok({"content": "..."})`

Settings: `{"action": "set", "content": "new system prompt"}` → `ok({"content": "..."})`

### tool ↔ prompt conversion

**handler**: `defaults.prompt.convert`（`blocks/prompt/convert.py`）

**HTTP**: `POST /api/prompts/convert`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `source_type` | `string` | Yes | `"tool"` or `"prompt"` |
| `source_name` | `string` | Yes | Source name |
| `target_type` | `string` | Yes | `"tool"` or `"prompt"` (must be different from source_type) |

**tool → prompt**: Convert tool's `parameters` into a variable and `summary` into a template body header. `PromptTemplate.from_tool_schema()` is used.

**prompt → tool**: Invalid as an authoring route. `execution.type: "prompt"` tool will not be created. If necessary, call `defaults.prompt.render` from a flow/function, and if you need a tool, define it separately as a `rumi_function` or `capability` facade.

## Example of getting context

```python
# プロンプトを作成（call_handler 経由）
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_aware",
    "content": "Messages so far: {{context.message_count}}\nConversation: {{context.conversation_id}}\n\nUser request: {{request}}",
    "variables": [{"name": "request", "type": "string", "required": True}]
})
```

When you pass context at render time, `inject_context_variables()` will auto-inject `context.message_count` and `context.conversation_id`.

## Specific example

### Example 1: Code review prompt

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

### Example 2: Translation prompt

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

### Example 3: Context-aware summary prompt

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_summary",
    "content": "Conversation has {{context.message_count}} messages ({{context.total_tokens}} tokens).\n\nPlease summarize the conversation so far, focusing on: {{focus}}\n\nMessages:\n{{context.messages}}",
    "variables": [
        {"name": "focus", "type": "string", "default": "key decisions and action items"}
    ]
})
```

## Best practices

`name` should be a name that clearly describes the purpose of the prompt. This makes it easier to identify them in the list of prompts.

Please set `required: true` appropriately in `variables`. If a required variable is unspecified, `{{variable_name}}` remains in the output.

Use the `{{context.*}}` variable to automatically inject context information at runtime into `content` (body). If the user explicitly specifies a value, it will not be overwritten, so you can pass mock values ​​when testing.

The authoring route that automatically generates a tool from a prompt is invalid. `context.*` variables are resolved passively by `defaults.prompt.resolve_for_conversation` and are defined separately as a `rumi_function` / `capability` facade if a tool is required.

Persistence files (`user_data/shared/prompts/`) are managed by `PromptManager`. The file name is generated by `_safe_filename(name) + ".json"`, and characters other than alphanumeric characters, hyphens, and underscores are converted to underscores.
