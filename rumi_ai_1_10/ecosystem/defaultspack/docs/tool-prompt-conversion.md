# Tool ↔ Prompt 変換ガイド

## 1. 構造の共通性

rumiai defaults において tool と prompt は構造的に対称な存在である。

tool は「パラメータを受け取り結果を返す関数」であり、定義は schema.json + handler.py で構成される。prompt は「変数を受け取りテキストを返す関数」であり、定義は VARIABLES + template.md（または prompt.py）で構成される。

両者の対応関係は以下の通りである。

| tool の概念 | prompt の概念 |
|---|---|
| `tool_id` | `prompt_id` |
| `schema.json` の `parameters` | `VARIABLES` の `required` + `optional` + `custom` |
| `handler.py` の `run(params, context)` | `prompt.py` の `pre_render(variables, context)` |
| `handler.py` の戻り値 `{"result": ...}` | レンダリング後のテキスト文字列 |
| `guide.json` の `purpose` / `when_to_use` | `METADATA` の `description` |
| `conditions.json` | 該当なし（prompt はモデル条件を持たない） |
| `permission.json` の `capabilities_required` | `PERMISSIONS` |
| `tool.json` の `tags` | `METADATA` の `tags` |

この対称性により、tool と prompt の間の双方向変換が可能である。


## 2. Tool → Prompt 変換

### 2.1 変換の目的

tool 定義を prompt のテンプレート変数として再利用する場合に使う。たとえば「ツールの使い方を LLM に教えるプロンプト」を自動生成する、ツールのスキーマからフォーム入力用のプロンプトを生成する、といったユースケースがある。

### 2.2 変換ルール

tool の `schema.json` の `parameters.properties` を prompt の `VARIABLES` に変換する。各プロパティの `type` と `description` がそのまま変数定義になる。`required` 配列に含まれるプロパティは `VARIABLES.required` に、含まれないものは `VARIABLES.optional` に配置される。`default` 値があればそのまま引き継ぐ。

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

tool の `guide.json` からテンプレートのベース構造を生成する。`purpose` がテンプレートの冒頭説明になり、`examples` が few-shot 例として埋め込まれる。

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

| tool フィールド | prompt フィールド |
|---|---|
| `tool.json` の `tool_id` | `METADATA["prompt_id"]` に `"tool_prompt_{tool_id}"` |
| `tool.json` の `name` | `METADATA["name"]` |
| `tool.json` の `summary` | `METADATA["description"]` |
| `tool.json` の `version` | `METADATA["version"]` |
| `tool.json` の `tags` | `METADATA["metadata"]["tags"]` |
| `permission.json` の capabilities | `PERMISSIONS` |


## 3. Prompt → Tool 変換

### 3.1 変換の目的

prompt を LLM の tool_call として呼び出し可能にする場合に使う。たとえば agent がプロンプトのレンダリングをツールとして使いたい場合、プロンプト定義から tool のスキーマを自動生成できる。

### 3.2 変換ルール

prompt の `VARIABLES` の各変数を `schema.json` の `parameters.properties` に変換する。`required` 変数は `parameters.required` 配列に含める。`optional` と `custom` は `default` 値付きのプロパティになる。

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

handler.py は自動的に `defaults.prompt.render` を `call_handler` で呼び出すラッパーになる。

```python
# 自動生成される handler.py
def run(params, context):
    rendered = context["call_handler"]("defaults.prompt.render", {
        "prompt_id": "TARGET_PROMPT_ID",
        "variables": params,
    })
    return {"result": rendered}
```


## 4. ラウンドトリップの注意点

tool → prompt → tool の往復変換（ラウンドトリップ）では情報の欠落が発生する。

tool 固有の情報で prompt に変換できないもの: `conditions.json`（モデル条件）、`relations.json`（連携ツール）、`permission.json` の `parameter_restrictions`（パラメータ制限）、`execution` 設定（実行タイプ、タイムアウト）。これらは変換時に失われる。

prompt 固有の情報で tool に変換できないもの: `extends`（テンプレート継承）、`pre_render` / `post_render` のロジック、`include` で参照される partials、`source: system` の変数。

ラウンドトリップが必要な場合は、元の定義を保持した上で変換結果を利用することを推奨する。変換結果だけで元を復元することは保証されない。


## 5. API の使い方

変換は handler 経由で行う。

### tool → prompt 変換

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

### prompt → tool 呼び出し

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

### 例1: ツール定義からドキュメントを自動生成

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

### 例2: プロンプトを tool_call として LLM に公開

エージェントが system prompt の変更を tool_call で動的に行う例。

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

### 例3: 複数ツールの統合ガイドを prompt で生成

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
