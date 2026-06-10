<!-- docs-i18n-links:start -->
[EN](./writing-tools.md) | [JP](./i18n/ja/writing-tools.md) | [KR](./i18n/ko/writing-tools.md) | [CN](./i18n/zh-cn/writing-tools.md)
<!-- docs-i18n-links:end -->

# Writing Tools

A guide to creating and managing dynamic tools with defaults pack. Tool-related handlers are implemented in `blocks/tool/`, and domain logic is implemented in `domain/tool/registry.py` (ToolRegistry) and `domain/tool/builder.py`.

## Tool concept

A tool is a unit of functionality that the agent calls based on the AI's judgment. Each tool has parameter definitions using JSON Schema and execution logic (handler_code) using Python code.

There are two types of tools.

**Built-in tool** (`execution.type: "local"`) is a demonstration tool that is automatically registered with `ToolRegistry._register_defaults()`. Three items will be registered: `web_search`, `calculator`, and `file_reader`.

**Dynamic Tools** (`execution.type: "dynamic"`) are user-defined tools that can be created, updated, and deleted via the API. It is persisted in the `user_data/shared/tools/` directory as `.tool.json` (definition) and `.handler.py` (execution code).

## tool definition JSON format

The tool definition has the following structure.

```json
{
  "tool_id": "my_tool",
  "name": "my_tool",
  "summary": "ツールの説明文",
  "tags": ["dynamic", "user-created"],
  "schema": {
    "parameters": {
      "type": "object",
      "properties": {
        "param1": {"type": "string"},
        "param2": {"type": "integer"}
      },
      "required": ["param1"]
    }
  },
  "execution": {"type": "dynamic"},
  "created_at": "2025-01-01T00:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `tool_id` | `string` | Unique identifier for the tool. Usually the same as `name` |
| `name` | `string` | Tool name |
| `summary` | `string` | Tool description. Referenced by AI when selecting tools |
| `tags` | `string[]` | Tag. Used for filtering |
| `schema.parameters` | `object` | Parameter definition in JSON Schema format |
| `execution.type` | `string` | Any of `"local"`, `"dynamic"`, `"prompt"` |
| `created_at` | `string` | Creation date and time (ISO 8601) |
| `updated_at` | `string` | Date and time of update (ISO 8601). Automatically granted upon renewal |

## How to write handler_code

handler_code is written as a `handler` function with the following signature.

```python
def handler(arguments, context):
    """
    arguments: dict — schema.parameters で定義されたキーを持つ dict
    context: dict — 実行コンテキスト

    Returns: dict with keys:
        "result": str     — 実行結果のテキスト
        "is_error": bool  — エラーかどうか
        "widget": dict|None — UI に表示する Widget（任意）
    """
    param1 = arguments.get("param1", "")
    # ... ロジック ...
    return {
        "result": "Success: " + param1,
        "is_error": False,
        "widget": None,
    }
```

**Arguments**: `arguments` is a dict of parameters passed during the API call. `context` is the execution context of handler and may contain functions such as `call_handler`, `emit_event`, etc.

**Return value**: Returns a dict with three keys: `result` (string), `is_error` (bool), `widget` (dict or None).

**Limitations**: handler_code may be AI-generated in `generate_handler_code_with_ai()` of `domain/tool/builder.py`. If `handler_code` is `None`, AI will automatically generate it, and if AI is unavailable, skeleton code will be generated in `generate_skeleton()`.

## CRUD via API

### Tool creation

**HTTP**: `POST /api/tools/create`（`blocks/tool/create.py`）

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name |
| `description` | `string` | No | Explanation |
| `parameters` | `object` | Yes | JSON Schema format parameter definition |
| `handler_code` | `string` | No | Python code. In case of `None`, AI automatically generates |
| `tags` | `string[]` | No | Tag. Default `["dynamic", "user-created"]` |
| `model` | `string` | No | handler_code AI model used for automatic generation |

If a tool with the same name already exists, a `ALREADY_EXISTS` error will be returned.

**Return value**: `ok({"tool_id": "...", "name": "...", "summary": "...", "handler_code": "...", "created_at": "..."})`

### Tool update

**HTTP**: `PUT /api/tools/{name}`（`blocks/tool/update.py`）

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update. Changes to `name` and `tool_id` are prohibited |

Only dynamic tools (`execution.type: "dynamic"`) can be updated. `updated_at` will be granted automatically.

**Return value**: `ok({"tool_id": "...", "name": "...", "summary": "...", "tags": [...], "updated_at": "..."})`

### Delete tools

**HTTP**: `DELETE /api/tools/{name}`（`blocks/tool/delete.py`）

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name (automatically injected from URL path) |

Only dynamic tools can be deleted. `.tool.json` and `.handler.py` within `user_data/shared/tools/` are also removed.

**Return value**: `ok({"deleted": "tool_name", "tool_id": "..."})`

### Tool Export

**HTTP**: `GET /api/tools/{name}/export`（`blocks/tool/export.py`）

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | No | Single tool name |
| `names` | `string[]` | No | Multiple tool names (exclusive with `name`) |

**Return value**: `ok({"tools": [...], "count": N, "not_found": [...]})`. Each tool is a complete definition including `handler_code`.

## Specific example

### Example 1: Calculator

```bash
curl -X POST http://127.0.0.1:8766/api/tools/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "unit_converter",
    "description": "単位変換を行うツール",
    "parameters": {
      "type": "object",
      "properties": {
        "value": {"type": "number"},
        "from_unit": {"type": "string"},
        "to_unit": {"type": "string"}
      },
      "required": ["value", "from_unit", "to_unit"]
    },
    "handler_code": "def handler(arguments, context):\n    value = arguments.get(\"value\", 0)\n    from_u = arguments.get(\"from_unit\", \"\")\n    to_u = arguments.get(\"to_unit\", \"\")\n    conversions = {(\"km\", \"m\"): 1000, (\"m\", \"km\"): 0.001, (\"kg\", \"g\"): 1000, (\"g\", \"kg\"): 0.001}\n    factor = conversions.get((from_u, to_u))\n    if factor is None:\n        return {\"result\": \"Unsupported conversion: \" + from_u + \" to \" + to_u, \"is_error\": True, \"widget\": None}\n    result_val = value * factor\n    return {\"result\": str(result_val) + \" \" + to_u, \"is_error\": False, \"widget\": None}"
  }'
```

### Example 2: Let AI automatically generate handler_code

```bash
curl -X POST http://127.0.0.1:8766/api/tools/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "text_summarizer",
    "description": "長いテキストを要約するツール",
    "parameters": {
      "type": "object",
      "properties": {
        "text": {"type": "string"},
        "max_length": {"type": "integer"}
      },
      "required": ["text"]
    }
  }'
```

If you omit `handler_code`, the AI will generate the code if an AI provider is available. If unavailable, skeleton code will be generated.

### Example 3: Update tools

```bash
curl -X PUT http://127.0.0.1:8766/api/tools/unit_converter \
  -H "Content-Type: application/json" \
  -d '{
    "updates": {
      "summary": "単位変換ツール（拡張版）",
      "tags": ["dynamic", "math", "conversion"]
    }
  }'
```

## Best practices

Keep your `name` short and clear, with a one-word name that describes the tool's functionality. The AI ​​will refer to `name` and `summary` when selecting tools, so be sure to specifically describe the purpose of the tool in `summary`.

Please define the JSON Schema for `parameters` in as much detail as possible. Be sure to specify the required parameters in the `required` field and specify exactly the `type` for each property.

`handler_code` should always return a dict of the form `{"result": str, "is_error": bool, "widget": None}`. If an unexpected exception occurs, please return the result with `is_error: true`.

Do not edit the persistence file (`user_data/shared/tools/`) directly, but operate it via the API. `ToolRegistry` manages in-memory cache and file consistency.
