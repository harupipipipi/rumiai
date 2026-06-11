<!-- docs-i18n-links:start -->
[EN](../../tool-prompt-conversion.md) | [JP](../ja/tool-prompt-conversion.md) | [KR](./tool-prompt-conversion.md) | [CN](../zh-cn/tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# 도구 ⇔ 프롬프트 변환 안내

## 1. 구조의 공통성

루미아이 기본값에서는 도구와 프롬프트가 구조적으로 대칭입니다.

도구는 "매개변수를 받고 결과를 반환하는 함수"이며 정의는 Schema.json + handler.py로 구성됩니다. 프롬프트는 ``변수를 받고 텍스트를 반환하는 함수''이며 정의는 VARIABLES + template.md(또는 프롬프트.py)로 구성됩니다.

둘 사이의 대응관계는 다음과 같다.

| 도구의 개념 | 프롬프트의 개념 |
|---|---|
| `tool_id` | `prompt_id` |
| `parameters`의 `schema.json` | `required` of `VARIABLES` + `optional` + `custom` |
| `handler.py`의 `run(params, context)` | `prompt.py`의 `pre_render(variables, context)` |
| `handler.py` `{"result": ...}`의 반환 값 | 렌더링된 텍스트 문자열 |
| `guide.json` of `purpose` / `when_to_use` | `METADATA`의 `description` |
| `conditions.json` | 해당 없음(프롬프트에 모델 조건이 없음) |
| `permission.json`의 `capabilities_required` | `PERMISSIONS` |
| `tool.json`의 `tags` | `METADATA`의 `tags` |

이러한 대칭을 통해 도구와 프롬프트 간의 양방향 변환이 가능해집니다.


## 2. 도구 → 프롬프트 변환

### 2.1 변환 목적

도구 정의를 프롬프트 템플릿 변수로 재사용할 때 사용됩니다. 예를 들어 LLM에게 도구 사용 방법을 가르치기 위한 프롬프트를 자동으로 생성하거나 도구 스키마에서 양식 입력을 위한 프롬프트를 생성하는 등의 사용 사례가 있습니다.

### 2.2 변환 규칙

도구의 `schema.json`의 `parameters.properties`를 프롬프트의 `VARIABLES`로 변환합니다. 각 속성의 `type`, `description`는 그대로 변수 정의가 됩니다. `required` 배열에 포함된 속성은 `VARIABLES.required`에 배치되고, 배열에 포함되지 않은 속성은 `VARIABLES.optional`에 배치됩니다. `default` 값이 있으면 그대로 상속됩니다.

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

`guide.json` 도구에서 템플릿의 기본 구조를 생성합니다. `purpose`은 템플릿의 시작 설명이 되고, `examples`는 몇 장의 예시로 포함됩니다.

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

### 2.3 메타데이터 변환

| 도구 분야 | 프롬프트 필드 |
|---|---|
| `tool.json`의 `tool_id` | `METADATA["prompt_id"]`의 `"tool_prompt_{tool_id}"` |
| `tool.json`의 `name` | `METADATA["name"]` |
| `tool.json`의 `summary` | `METADATA["description"]` |
| `tool.json`의 `version` | `METADATA["version"]` |
| `tool.json`의 `tags` | `METADATA["metadata"]["tags"]` |
| `permission.json` 기능 | `PERMISSIONS` |


## 3. 프롬프트 → 도구 변환

### 3.1 변환 목적

LLM의 tool_call로 프롬프트 호출이 가능하도록 만드는 데 사용됩니다. 예를 들어 에이전트가 프롬프트 렌더링을 도구로 사용하려는 경우 프롬프트 정의에서 도구 스키마를 자동으로 생성할 수 있습니다.

### 3.2 변환 규칙

프롬프트의 `VARIABLES`의 각 변수를 `schema.json`의 `parameters.properties`로 변환합니다. `required` 변수는 `parameters.required` 배열에 포함됩니다. `optional` 및 `custom`는 `default` 가치 속성이 됩니다.

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

handler.py는 자동으로 `call_handler`로 `defaults.prompt.render`를 호출하는 래퍼가 됩니다.

```python
# 自動生成される handler.py
def run(params, context):
    rendered = context["call_handler"]("defaults.prompt.render", {
        "prompt_id": "TARGET_PROMPT_ID",
        "variables": params,
    })
    return {"result": rendered}
```


## 4. 왕복여행 시 주의사항

공구 → 프롬프트 → 공구의 왕복 변환 시 정보가 손실됩니다.

프롬프트로 변환할 수 없는 도구별 정보: `conditions.json`(모델 조건), `relations.json`(협동 도구), `permission.json`의 `parameter_restrictions`(매개변수 제한), `execution` 설정(실행 유형, 시간 초과). 이는 변환 중에 손실됩니다.

도구로 변환할 수 없는 프롬프트 관련 정보: `extends`(템플릿 상속), `pre_render` / `post_render`의 논리, `include`에서 참조된 부분, `source: system`의 변수.

왕복이 필요한 경우 원래 정의를 유지하고 변환 결과를 사용하는 것이 좋습니다. 변환 결과만으로는 원본 복원이 보장되지 않습니다.


## 5. API 사용방법

변환은 핸들러를 통해 수행됩니다.

### 도구 → 프롬프트 변환

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

### 프롬프트 → 도구 호출

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


## 6. 실제 사례

### 예시 1: 도구 정의에서 자동으로 문서 생성

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

### 예시 2: LLM에 프롬프트를 tool_call로 노출

tool_call을 사용하여 시스템 프롬프트를 동적으로 변경하는 에이전트의 예입니다.

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

### 예시 3: 프롬프트가 포함된 다중 도구 통합 가이드 생성

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
