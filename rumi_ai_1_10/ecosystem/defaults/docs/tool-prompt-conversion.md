<!-- docs-i18n-links:start -->
[EN](./tool-prompt-conversion.md) | [JP](./i18n/ja/tool-prompt-conversion.md) | [KR](./i18n/ko/tool-prompt-conversion.md) | [CN](./i18n/zh-cn/tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# Tool ↔ Prompt conversion guide

## 1. Commonality of structure

In rumiai defaults, tool and prompt are structurally symmetrical.

tool is a "function that receives parameters and returns results" and its definition consists of schema.json + handler.py. prompt is a ``function that receives variables and returns text,'' and its definition consists of VARIABLES + template.md (or prompt.py).

The correspondence relationship between the two is as follows.

| Concept of tool | Concept of prompt |
|---|---|
| `tool_id` | `prompt_id` |
| `parameters` of `schema.json` | `required` of `VARIABLES` + `optional` + `custom` |
| `handler.py` of `run(params, context)` | `prompt.py` of `pre_render(variables, context)` |
| Return value of `handler.py` `{"result": ...}` | Rendered text string |
| `guide.json` of `purpose` / `when_to_use` | `METADATA` of `description` |
| `conditions.json` | Not applicable (prompt has no model condition) |
| `permission.json` of `capabilities_required` | `PERMISSIONS` |
| `tool.json` of `tags` | `METADATA` of `tags` |

This symmetry allows bidirectional conversion between tool and prompt.


## 2. Tool → Prompt conversion

### 2.1 Purpose of conversion

Used when reusing the tool definition as a prompt template variable. For example, there are use cases such as automatically generating prompts to teach an LLM how to use a tool, or generating prompts for form input from a tool's schema.

### 2.2 Conversion rules

Convert `parameters.properties` of tool's `schema.json` to prompt's `VARIABLES`. `type` and `description` of each property become variable definitions as they are. Properties included in the `required` array are placed in `VARIABLES.required`, and those not included in the array are placed in `VARIABLES.optional`. `default` If there is a value, it will be inherited as is.

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

Generate the base structure of the template from the tool `guide.json`. `purpose` becomes the opening explanation of the template, and `examples` is embedded as a few-shot example.

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

### 2.3 Metadata conversion

| tool field | prompt field |
|---|---|
| `tool.json` of `tool_id` | `METADATA["prompt_id"]` of `"tool_prompt_{tool_id}"` |
| `tool.json` of `name` | `METADATA["name"]` |
| `tool.json` of `summary` | `METADATA["description"]` |
| `tool.json` of `version` | `METADATA["version"]` |
| `tool.json` of `tags` | `METADATA["metadata"]["tags"]` |
| `permission.json` capabilities | `PERMISSIONS` |


## 3. Prompt → Tool conversion

### 3.1 Purpose of conversion

Used to make prompt callable as LLM's tool_call. For example, if an agent wants to use prompt rendering as a tool, it can automatically generate the tool schema from the prompt definition.

### 3.2 Conversion rules

Convert each variable of `VARIABLES` of prompt to `parameters.properties` of `schema.json`. `required` Variables are included in the `parameters.required` array. `optional` and `custom` become `default` valued properties.

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

handler.py automatically becomes a wrapper that calls `defaults.prompt.render` with `call_handler`.

```python
# 自動生成される handler.py
def run(params, context):
    rendered = context["call_handler"]("defaults.prompt.render", {
        "prompt_id": "TARGET_PROMPT_ID",
        "variables": params,
    })
    return {"result": rendered}
```


## 4. Notes on round trips

Information is lost in the round-trip conversion of tool → prompt → tool.

Tool-specific information that cannot be converted into a prompt: `conditions.json` (model conditions), `relations.json` (cooperative tools), `parameter_restrictions` (parameter restrictions) of `permission.json`, `execution` settings (execution type, timeout). These are lost during conversion.

Information specific to prompt that cannot be converted to tool: `extends` (template inheritance), logic in `pre_render` / `post_render`, partials referenced in `include`, variables in `source: system`.

If a round trip is required, it is recommended to retain the original definition and use the conversion result. It is not guaranteed that the original can be restored based on the conversion result alone.


## 5. How to use the API

Conversion is done via handler.

### tool → prompt conversion

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

### prompt → tool call

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


## 6. Practical examples

### Example 1: Automatically generate documentation from tool definition

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

### Example 2: Expose prompt to LLM as tool_call

An example of an agent dynamically changing the system prompt using tool_call.

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

### Example 3: Generate multi-tool integration guide with prompt

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
