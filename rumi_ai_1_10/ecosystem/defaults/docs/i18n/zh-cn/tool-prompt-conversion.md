<!-- docs-i18n-links:start -->
[EN](../../tool-prompt-conversion.md) | [JP](../ja/tool-prompt-conversion.md) | [KR](../ko/tool-prompt-conversion.md) | [CN](./tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# 工具 ↔ 提示转换指南

## 1.结构的共性

在rumiai默认设置中，工具和提示在结构上是对称的。

tool 是一个“接收参数并返回结果的函数”，其定义由 schema.json + handler.py 组成。 Prompt 是一个“接收变量并返回文本的函数”，其定义由 VARIABLES + template.md（或 Prompt.py）组成。

两者的对应关系如下。

|工具的概念|提示的概念|
|---|---|
| §鲁米§0§| §鲁米§1§ |
| `parameters` 之 `schema.json` | `required` of `VARIABLES` + `optional` + `custom` |
| `handler.py` 之 `run(params, context)` | `prompt.py` 或 `pre_render(variables, context)` |
|返回值`handler.py``{"result": ...}`|渲染文本字符串 |
| `guide.json` 之 `purpose` / `when_to_use` | `METADATA` 或 `description` |
| §鲁米§0§|不适用（提示无型号条件）|
| `permission.json` 之 `capabilities_required` | §鲁米§2§ |
| `tool.json` 之 `tags` | `METADATA` 或 `tags` |

这种对称性允许工具和提示之间的双向转换。


## 2.工具→提示转换

### 2.1 转换的目的

在将工具定义重新用作提示模板变量时使用。例如，有一些用例，例如自动生成提示来教法学硕士如何使用工具，或者从工具的模式生成表单输入的提示。

### 2.2 转换规则

将工具的`schema.json`的`parameters.properties`转换为提示的`VARIABLES`。每个属性的`type`和`description`变成变量定义。 `required` 数组中包含的属性放置在`VARIABLES.required` 中，数组中未包含的属性放置在`VARIABLES.optional` 中。 `default` 如果有值，它将按原样继承。

```python
# 変換の疑似コード
def tool_to_prompt_variables(schema: dict) -> dict:
    params = schema["parameters"]
    required_names = set(params.get("required", []))
    variables = {"required": [], "optional": [], "custom": []}

    for name, prop in params["properties"].items():
        var_def = {
            "name": name,
            "type": prop["type"],
            "description": prop.get("description", ""),
        }
        if name in required_names:
            variables["required"].append(var_def)
        else:
            if "default" in prop:
                var_def["default"] = prop["default"]
            variables["optional"].append(var_def)

    return variables
```

从工具`guide.json`生成模板的基本结构。 `purpose` 成为模板的开头解释，`examples` 被嵌入作为几个镜头示例。

```markdown
{# 自動生成されたテンプレート #}
{{ purpose }}

{% for example in examples %}
## 例{{ loop.index }}: {{ example.description }}
入力: {{ example.input | tojson }}
{% endfor %}

ユーザーの入力:
{{ user_input }}
```

### 2.3 元数据转换

|工具领域|提示字段|
|---|---|
| `tool.json` 之 `tool_id` | `METADATA["prompt_id"]` 或 `"tool_prompt_{tool_id}"` |
| `tool.json` 之 `name` | §鲁米§2§ |
| `tool.json` 之 `summary` | §鲁米§2§ |
| `tool.json` 之 `version` | §鲁米§2§ |
| `tool.json` 之 `tags` | §鲁米§2§ |
| `permission.json`能力| §鲁米§1§ |


## 3.提示→工具转换

### 3.1 转换的目的

用于使提示可作为 LLM 的 tool_call 进行调用。例如，如果代理想要使用提示渲染作为工具，它可以根据提示定义自动生成工具模式。

### 3.2 转换规则

将提示`VARIABLES`的每个变量转换为`schema.json`的`parameters.properties`。 `required` 变量包含在`parameters.required` 数组中。 `optional` 和`custom` 成为`default` 有价值的属性。

```python
def prompt_to_tool_schema(variables: dict) -> dict:
    properties = {}
    required = []

    for var in variables.get("required", []):
        properties[var["name"]] = {
            "type": var.get("type", "string"),
            "description": var.get("description", ""),
        }
        required.append(var["name"])

    for var in variables.get("optional", []) + variables.get("custom", []):
        prop = {
            "type": var.get("type", "string"),
            "description": var.get("description", ""),
        }
        if "default" in var:
            prop["default"] = var["default"]
        properties[var["name"]] = prop

    return {
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
        "returns": {
            "type": "object",
            "properties": {
                "rendered_text": {
                    "type": "string",
                    "description": "レンダリングされたプロンプトテキスト",
                }
            },
        },
    }
```

handler.py 自动成为一个使用 `call_handler` 调用 `defaults.prompt.render` 的包装器。

```python
# 自動生成される handler.py
def run(params, context):
    rendered = context["call_handler"]("defaults.prompt.render", {
        "prompt_id": "TARGET_PROMPT_ID",
        "variables": params,
    })
    return {"result": rendered}
```


## 4. 往返注意事项

在工具→提示→工具的往返转换中信息丢失。

无法转换为提示的工具特定信息：`conditions.json`（模型条件）、`relations.json`（协作工具）、`parameter_restrictions`（参数限制）、`permission.json`、`execution`设置（执行类型、超时）。这些在转换过程中会丢失。

无法转换为工具的提示特定信息：`extends`（模板继承）、`pre_render`/`post_render`中的逻辑、​​`include`中引用的部分、`source: system`中的变量。

如果需要往返，建议保留原来的定义，使用转换结果。不保证仅根据转换结果就能恢复原样。


## 5. 如何使用API

转换是通过处理程序完成的。

###工具→提示转换

```python
# tool の handler.py 内で
tool_schema = context["call_handler"]("defaults.tool.schema", {
    "tool_name": "file_read"
})

# schema から変数定義を手動で構築し、prompt.render に渡す
rendered = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "tool_usage_guide",
    "variables": {
        "tool_name": "file_read",
        "tool_schema": tool_schema,
    }
})
```

###提示→工具调用

```python
# agent やフロー内で prompt をツールとして使う
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "coding_system",
    "variables": {
        "agent_name": "Coding Assistant",
        "tools": tool_list,
        "project_memory": memory_content,
    }
})
# result は文字列（レンダリング済みプロンプト）
```


## 6. 实际例子

### 示例 1：根据工具定义自动生成文档

```python
def run(params, context):
    tools = context["call_handler"]("defaults.tool.list", {})
    docs = []

    for tool in tools:
        schema = context["call_handler"]("defaults.tool.schema", {
            "tool_name": tool["tool_id"]
        })
        doc = context["call_handler"]("defaults.prompt.render", {
            "prompt_id": "tool_doc_template",
            "variables": {
                "tool_name": tool["name"],
                "summary": tool["summary"],
                "parameters": schema["parameters"],
                "examples": schema.get("examples", []),
            }
        })
        docs.append(doc)

    return {"result": "\n---\n".join(docs)}
```

### 示例 2：将提示作为 tool_call 公开给 LLM

代理使用 tool_call 动态更改系统提示的示例。

```python
# user_data/shared/tools/switch_persona/handler.py
def run(params, context):
    rendered = context["call_handler"]("defaults.prompt.render", {
        "prompt_id": params["persona_prompt_id"],
        "variables": params.get("variables", {}),
    })
    context["call_handler"]("defaults.prompt.system", {
        "conversation_id": params["conversation_id"],
        "content": rendered,
    })
    return {"result": f"Persona switched to {params['persona_prompt_id']}"}
```

### 示例 3：生成带有提示的多工具集成指南

```python
def run(params, context):
    tool_schemas = []
    for tool_id in params["tool_ids"]:
        schema = context["call_handler"]("defaults.tool.schema", {
            "tool_name": tool_id
        })
        tool_schemas.append(schema)

    rendered = context["call_handler"]("defaults.prompt.render", {
        "prompt_id": "multi_tool_guide",
        "variables": {"tools": tool_schemas},
    })
    return {"result": rendered}
```
