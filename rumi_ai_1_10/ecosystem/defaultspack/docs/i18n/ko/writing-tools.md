<!-- docs-i18n-links:start -->
[EN](../../writing-tools.md) | [JP](../ja/writing-tools.md) | [KR](./writing-tools.md) | [CN](../zh-cn/writing-tools.md)
<!-- docs-i18n-links:end -->

# 글쓰기 도구

기본 팩을 사용하여 동적 도구를 만들고 관리하는 방법에 대한 가이드입니다. 도구 관련 핸들러는 `blocks/tool/`에서 구현되며, 도메인 로직은 `domain/tool/registry.py`(ToolRegistry) 및 `domain/tool/builder.py`에서 구현됩니다.

## 도구 개념

도구는 AI의 판단에 따라 에이전트가 호출하는 기능 단위입니다. 각 도구에는 JSON 스키마를 사용하는 매개변수 정의와 Python 코드를 사용하는 실행 논리(handler_code)가 있습니다.

도구에는 두 가지 유형이 있습니다.

**내장 도구**(`execution.type: "local"`)는 `ToolRegistry._register_defaults()`에 자동으로 등록되는 데모 도구입니다. `web_search`, `calculator`, `file_reader`의 세 가지 항목이 등록됩니다.**동적 도구**(`execution.type: "dynamic"`)는 API를 통해 생성, 업데이트, 삭제할 수 있는 사용자 정의 도구입니다. 이는 `user_data/shared/tools/` 디렉토리에 `.tool.json`(정의) 및 `.handler.py`(실행 코드)으로 유지됩니다.

## 도구 정의 JSON 형식

도구 정의는 다음과 같은 구조를 갖습니다.

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
| `execution.type` | `string` | Authorable tool is `"rumi_function"` or `"capability"`. `"local"`, `"dynamic"`, `"prompt"` are only trusted first-party compatibility paths |
| `created_at` | `string` | Creation date and time (ISO 8601) |
| `updated_at` | `string` | Date and time of update (ISO 8601). Automatically granted upon renewal |

## handler_code 작성 방법

handler_code는 다음 서명을 사용하여 `handler` 함수로 작성됩니다.

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

**인수**: `arguments`은 API 호출 중에 전달된 매개변수의 사전입니다. `context`은 핸들러의 실행 컨텍스트이며 `call_handler`, `emit_event` 등과 같은 기능을 포함할 수 있습니다.**반환 값**: `result`(문자열), `is_error`(부울), `widget`(dict 또는 None)의 세 가지 키가 있는 사전을 반환합니다.**제한 사항**: handler_code는 `domain/tool/builder.py`의 `generate_handler_code_with_ai()`에서 AI로 생성될 수 있습니다. `handler_code`가 `None`이면 AI가 자동으로 생성하고, AI가 불가능한 경우 `generate_skeleton()`에서 스켈레톤 코드를 생성합니다.

## API를 통한 CRUD

### 도구 생성

**HTTP**: `POST /api/tools/create`(`blocks/tool/create.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name |
| `description` | `string` | No | Explanation |
| `parameters` | `object` | Yes | JSON Schema format parameter definition |
| `handler_code` | `string` | No | Python code. In case of `None`, AI automatically generates |
| `tags` | `string[]` | No | Tag. Default `["dynamic", "user-created"]` |
| `model` | `string` | No | handler_code AI model used for automatic generation |

동일한 이름의 도구가 이미 존재하는 경우 `ALREADY_EXISTS` 오류가 반환됩니다.

**반환 값**: `ok({"tool_id": "...", "name": "...", "summary": "...", "handler_code": "...", "created_at": "..."})`

### 도구 업데이트

**HTTP**: `PUT /api/tools/{name}`(`blocks/tool/update.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update. Changes to `name` and `tool_id` are prohibited |

동적 도구(`execution.type: "dynamic"`)만 업데이트할 수 있습니다. `updated_at`은 자동으로 부여됩니다.

**반환 값**: `ok({"tool_id": "...", "name": "...", "summary": "...", "tags": [...], "updated_at": "..."})`

### 삭제 도구

**HTTP**: `DELETE /api/tools/{name}`(`blocks/tool/delete.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name (automatically injected from URL path) |

동적 도구만 삭제할 수 있습니다. `user_data/shared/tools/` 내의 `.tool.json` 및 `.handler.py`도 제거됩니다.

**반환 값**: `ok({"deleted": "tool_name", "tool_id": "..."})`

### 도구 내보내기

**HTTP**: `GET /api/tools/{name}/export`(`blocks/tool/export.py`)**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | No | Single tool name |
| `names` | `string[]` | No | Multiple tool names (exclusive with `name`) |

**반환 값**: `ok({"tools": [...], "count": N, "not_found": [...]})`. 각 도구는 `handler_code`을 포함한 완전한 정의입니다.

## 구체적인 예

### 예시 1: 계산기

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

### 예시 2: AI가 자동으로 handler_code를 생성하도록 허용

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

`handler_code`을 생략하면 AI 제공업체가 있는 경우 AI가 코드를 생성합니다. 사용할 수 없는 경우 뼈대 코드가 생성됩니다.

### 예시 3: 업데이트 도구

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

## 모범 사례

도구의 기능을 설명하는 한 단어 이름으로 `name`을 짧고 명확하게 유지하세요. AI는 도구를 선택할 때 `name` 및 `summary`를 참조하므로 `summary`에 도구의 목적을 구체적으로 설명해야 합니다.

`parameters`에 대한 JSON 스키마를 최대한 자세히 정의하십시오. `required` 필드에 필수 매개변수를 지정하고 각 속성에 대해 정확히 `type`를 지정해야 합니다.

`handler_code`은 항상 `{"result": str, "is_error": bool, "widget": None}` 형식의 사전을 반환해야 합니다. 예상치 못한 예외가 발생하면 `is_error: true`로 결과를 반환해 주세요.

지속성 파일(`user_data/shared/tools/`)을 직접 편집하지 말고 API를 통해 작동하십시오. `ToolRegistry`은 메모리 내 캐시와 파일 일관성을 관리합니다.
