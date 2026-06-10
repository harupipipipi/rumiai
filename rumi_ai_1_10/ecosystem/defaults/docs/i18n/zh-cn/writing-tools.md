<!-- docs-i18n-links:start -->
[EN](../../writing-tools.md) | [JP](../ja/writing-tools.md) | [KR](../ko/writing-tools.md) | [CN](./writing-tools.md)
<!-- docs-i18n-links:end -->

# 书写工具

使用默认包创建和管理动态工具的指南。与工具相关的处理程序在`blocks/tool/`中实现，域逻辑在`domain/tool/registry.py`（ToolRegistry）和`domain/tool/builder.py`中实现。

## 工具概念

工具是代理根据人工智能的判断调用的功能单元。每个工具都有使用 JSON Schema 的参数定义和使用 Python 代码的执行逻辑 (handler_code)。

有两种类型的工具。

**内置工具** (`execution.type: "local"`) 是一个演示工具，自动注册到`ToolRegistry._register_defaults()`。将注册三个项目：`web_search`、`calculator`和`file_reader`。

**动态工具** (`execution.type: "dynamic"`) 是用户定义的工具，可以通过 API 创建、更新和删除。它以`.tool.json`（定义）和`.handler.py`（执行代码）的形式保留在`user_data/shared/tools/`目录中。

## 工具定义JSON格式

工具定义具有以下结构。

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

|领域 |类型 |描述 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ |该工具的唯一标识符。通常与`name` | 相同
| §鲁米§0§| §鲁米§1§ |工具名称|
| §鲁米§0§| §鲁米§1§ |工具说明。 AI选择工具时参考 |
| §鲁米§0§| §鲁米§1§ |标签。用于过滤 |
| §鲁米§0§| §鲁米§1§ | JSON Schema 格式的参数定义 |
| §鲁米§0§| §鲁米§1§ | `"local"`、`"dynamic"`、`"prompt"` 中的任何一项 |
| §鲁米§0§| §鲁米§1§ |创建日期和时间 (ISO 8601) |
| §鲁米§0§| §鲁米§1§ |更新日期和时间 (ISO 8601)。续订时自动授予 |

## 如何编写handler_code

handler_code 被编写为具有以下签名的 `handler` 函数。

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

**参数**：`arguments` 是 API 调用期间传递的参数的字典。 `context`是处理程序的执行上下文，可能包含`call_handler`、`emit_event`等函数。

**返回值**：返回具有三个键的字典：`result`（字符串），`is_error`（布尔），`widget`（字典或无）。

**限制**：handler_code 可能是由 AI 在`domain/tool/builder.py` 的`generate_handler_code_with_ai()` 中生成的。如果`handler_code`是`None`，AI会自动生成它，如果AI不可用，骨架代码将在`generate_skeleton()`中生成。

## 通过 API 进行增删改查

### 工具创建

**HTTP**：`POST /api/tools/create`（`blocks/tool/create.py`）

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |工具名称|
| §鲁米§0§| §鲁米§1§ |没有 |说明|
| §鲁米§0§| §鲁米§1§ |是的 | JSON Schema 格式参数定义 |
| §鲁米§0§| §鲁米§1§ |没有 | Python 代码。如果是`None`，AI会自动生成|
| §鲁米§0§| §鲁米§1§ |没有 |标签。默认`["dynamic", "user-created"]` |
| §鲁米§0§| §鲁米§1§ |没有 | handler_code 用于自动生成的AI模型 |

如果同名工具已存在，则会返回`ALREADY_EXISTS`错误。

**返回值**：`ok({"tool_id": "...", "name": "...", "summary": "...", "handler_code": "...", "created_at": "..."})`

### 工具更新

**HTTP**：`PUT /api/tools/{name}`（`blocks/tool/update.py`）

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |工具名称（从 URL 路径自动注入）|
| §鲁米§0§| §鲁米§1§ |是的 |要更新的字段。禁止更改`name` 和`tool_id` |

仅动态工具 (`execution.type: "dynamic"`) 可以更新。 `updated_at` 将自动授予。

**返回值**：`ok({"tool_id": "...", "name": "...", "summary": "...", "tags": [...], "updated_at": "..."})`

### 删除工具

**HTTP**：`DELETE /api/tools/{name}`（`blocks/tool/delete.py`）

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |工具名称（从 URL 路径自动注入）|

只能删除动态工具。 `user_data/shared/tools/` 中的`.tool.json` 和`.handler.py` 也被删除。

**返回值**：`ok({"deleted": "tool_name", "tool_id": "..."})`

### 工具导出

**HTTP**：`GET /api/tools/{name}/export`（`blocks/tool/export.py`）

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |没有 |单一工具名称 |
| §鲁米§0§| §鲁米§1§ |没有 |多个工具名称（`name` 独有）|

**返回值**：`ok({"tools": [...], "count": N, "not_found": [...]})`。每个工具都是一个完整的定义，包括`handler_code`。

## 具体例子

### 示例 1：计算器

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

### 示例2：让AI自动生成handler_code

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

如果省略`handler_code`，如果 AI 提供商可用，AI 将生成代码。如果不可用，将生成骨架代码。

### 示例 3：更新工具

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

## 最佳实践

保持`name`简短、清晰，并使用一个单词名称来描述该工具的功能。 AI在选择工具时会参考`name`和`summary`，因此请务必在`summary`中具体描述该工具的用途。

请尽可能详细地定义`parameters`的JSON架构。请务必在`required`字段中指定所需的参数，并为每个属性准确指定`type`。

`handler_code` 应始终返回`{"result": str, "is_error": bool, "widget": None}` 形式的字典。如果发生意外异常，请使用`is_error: true`返回结果。

不要直接编辑持久性文件（`user_data/shared/tools/`），而是通过 API 对其进行操作。 `ToolRegistry` 管理内存缓存和文件一致性。
