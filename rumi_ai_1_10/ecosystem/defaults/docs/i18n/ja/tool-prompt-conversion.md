<!-- docs-i18n-links:start -->
[EN](../../tool-prompt-conversion.md) | [JP](./tool-prompt-conversion.md) | [KR](../ko/tool-prompt-conversion.md) | [CN](../zh-cn/tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# ツール ↔ プロンプト変換ガイド

## 1. 構造の共通性

rumiai のデフォルトでは、ツールとプロンプトは構造的に対称です。

tool は「パラメータを受け取って結果を返す関数」であり、その定義は schema.json + handler.py で構成されます。プロンプトは「変数を受け取ってテキストを返す関数」であり、その定義はVARIABLES + template.md (またはprompt.py)で構成されます。

両者の対応関係は以下の通りです。

|ツールのコンセプト |プロンプトの概念 |
|---|---|
| `tool_id` | `prompt_id` |
| `parameters` の `schema.json` | `required` の `VARIABLES` + `optional` + `custom` |
| `handler.py` の `run(params, context)` | `prompt.py`の`pre_render(variables, context)` |
| `handler.py` `{"result": ...}`の戻り値 |レンダリングされたテキスト文字列 |
| `guide.json` / `purpose` / `when_to_use` | `METADATA` の `description` |
| `conditions.json` |該当なし (プロンプトにモデル条件がありません) |
| `permission.json` の `capabilities_required` | `PERMISSIONS` |
| `tool.json` の `tags` | `METADATA`の`tags` |

この対称性により、ツールとプロンプト間の双方向変換が可能になります。


## 2. ツール → プロンプト変換

### 2.1 変換の目的

ツール定義をプロンプト テンプレート変数として再利用する場合に使用されます。たとえば、LLM にツールの使用方法を教えるプロンプトを自動的に生成したり、ツールのスキーマからフォーム入力のプロンプトを生成したりするユースケースがあります。

### 2.2 変換ルール

ツールの`schema.json`の`parameters.properties`をプロンプトの`VARIABLES`に変換します。各プロパティの`type`と`description`がそのまま変数定義となります。 `required` 配列に含まれるプロパティは `VARIABLES.required` に配置され、配列に含まれないプロパティは `VARIABLES.optional` に配置されます。 `default` 値があればそのまま継承されます。

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

`guide.json` ツールからテンプレートの基本構造を生成します。 `purpose`はテンプレートの冒頭の説明となり、`examples`は数ショットの例として埋め込まれます。

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

### 2.3 メタデータの変換

|ツールフィールド |プロンプトフィールド |
|---|---|
| `tool.json` の `tool_id` | `METADATA["prompt_id"]`の`"tool_prompt_{tool_id}"` |
| `tool.json` の `name` | `METADATA["name"]` |
| `tool.json` の `summary` | `METADATA["description"]` |
| `tool.json` の `version` | `METADATA["version"]` |
| `tool.json` の `tags` | `METADATA["metadata"]["tags"]` |
| `permission.json` の機能 | `PERMISSIONS` |


## 3. プロンプト→ツール変換

### 3.1 変換の目的

プロンプトを LLM の tools_call として呼び出し可能にするために使用されます。たとえば、エージェントがプロンプト レンダリングをツールとして使用したい場合、プロンプト定義からツール スキーマを自動的に生成できます。

### 3.2 変換ルール

プロンプトの`VARIABLES`の各変数を`schema.json`の`parameters.properties`に変換します。 `required` 変数は、`parameters.required` 配列に含まれます。 `optional` および `custom` は、`default` の値を持つプロパティになります。

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

handler.py は自動的に `call_handler` で `defaults.prompt.render` を呼び出すラッパーになります。

```python
# 自動生成される handler.py
def run(params, context):
    rendered = context["call_handler"]("defaults.prompt.render", {
        "prompt_id": "TARGET_PROMPT_ID",
        "variables": params,
    })
    return {"result": rendered}
```


＃＃４ 往復の注意事項

ツール→プロンプト→ツールの往復変換で情報が失われます。

プロンプトに変換できないツール固有の情報: `conditions.json`(モデル条件)、`relations.json`(連携ツール)、`parameter_restrictions`(パラメータ制限)、`permission.json`、`execution`の設定(実行タイプ、タイムアウト)。これらは変換中に失われます。

ツールに変換できないプロンプト固有の情報: `extends` (テンプレートの継承)、`pre_render` / `post_render` のロジック、`include` で参照される部分関数、`source: system` の変数。

ラウンドトリップが必要な場合は、元の定義を保持し、変換結果を使用することをお勧めします。変換結果だけでは元に戻せることを保証するものではありません。


## 5. APIの使用方法

変換はハンドラー経由で行われます。

### ツール → プロンプト変換

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

### プロンプト → ツール呼び出し

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


## 6. 実践例

### 例 1: ツール定義からドキュメントを自動生成する

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

### 例 2: プロンプトを tool_call として LLM に公開する

エージェントがtool_callを使用してシステム プロンプトを動的に変更する例。

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

### 例 3: プロンプト付きのマルチツール統合ガイドの生成

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
