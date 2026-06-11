<!-- docs-i18n-links:start -->
[EN](../../writing-prompts.md) | [JP](../ja/writing-prompts.md) | [KR](./writing-prompts.md) | [CN](../zh-cn/writing-prompts.md)
<!-- docs-i18n-links:end -->

# 프롬프트 작성

기본 팩을 사용하여 프롬프트 템플릿을 생성하고 관리하기 위한 가이드입니다. 핸들러는 `blocks/prompt/`에서 구현되고, 도메인 로직은 `domain/prompt/manager.py`(PromptManager), `domain/prompt/template.py`(PromptTemplate), `domain/prompt/renderer.py`(렌더링)에서 구현됩니다.

## 프롬프트 컨셉

프롬프트는 템플릿 변수를 포함하는 재사용 가능한 텍스트 템플릿입니다. `{{variable_name}}` 구문으로 변수를 삽입하고 렌더링 시 실제 값으로 대체합니다.

프롬프트는 메모리 내 dict + `user_data/shared/prompts/`에 대한 JSON 파일 지속성을 갖춘 `PromptManager`(싱글톤)에 의해 관리됩니다. 시작 시 JSON 파일에서 자동 로드됩니다.

프롬프트는 패시브 레이어입니다. 도구/공급자/권한을 선택하고 실행하지 않고 필요한 경우 흐름/기능에서 `defaults.prompt.render` 또는 `defaults.prompt.resolve_for_conversation`을 호출합니다.

## PromptTemplate의 형식

`domain/prompt/template.py`에 정의된 `PromptTemplate` 클래스의 구조.

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

지속되는 JSON 형식은 다음과 같습니다(`domain/prompt/manager.py`의 `create_prompt()`).

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

변수의 각 요소에는 다음과 같은 필드가 있습니다.

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Variable name |
| `type` | `string` | type (`"string"`, `"integer"`, etc.). Default `"string"` |
| `default` | `any` | Default value. None for `null` |
| `required` | `bool` | Is it required? Default `false` |

이전 형식(`variables: ["var1", "var2"]`)도 지원되며 `_normalize_variables()`에서 새 형식으로 자동 변환됩니다.

## 템플릿 변수

### 일반 변수

`{{variable_name}}`에 설명되어 있습니다. 렌더링 중에 `variables` dict의 값으로 대체되었습니다. `domain/prompt/renderer.py`의 `render()` 함수는 `_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")`를 사용하여 한 번에 대체합니다.

존재하지 않는 변수는 그대로 유지됩니다(오류가 발생하지 않음). 공백이 허용됩니다(`{{ name }}`도 유효함).

### 특수 변수(컨텍스트 변수)

`CONTEXT_VARIABLE_KEYS`은 `domain/prompt/template.py`에 정의되어 있습니다.

| Variable name | Type | Description |
|---|---|---|
| `{{context.total_tokens}}` | `int` | Total number of tokens in current context |
| `{{context.message_count}}` | `int` | Number of messages |
| `{{context.messages}}` | `string/list` | Message content. For list/dict, it is converted to JSON string |
| `{{context.system_prompt}}` | `string` | System prompt |
| `{{context.conversation_id}}` | `string` | Conversation ID |

특수 변수에는 `PromptManager.inject_context_variables(variables, context)`이 자동 주입됩니다. 사용자가 명시적으로 지정한 값은 덮어쓰이지 않습니다. 값은 컨텍스트 dict(`total_tokens`, `message_count` 등)의 해당 키에서 검색됩니다.

### 변수 추출 방법

`PromptTemplate` 클래스는 본문 내의 변수를 분석하는 방법을 제공합니다.

```python
template = PromptTemplate(body="Hello {{name}}, tokens: {{context.total_tokens}}")
template.extract_variable_names()   # → ["name", "context.total_tokens"]
template.list_user_variables()      # → ["name"]
template.list_context_variables()   # → ["context.total_tokens"]
```

## API를 통한 CRUD

### 프롬프트 생성

**처리자**: `defaults.prompt.create`(`blocks/prompt/create.py`)

HTTP 전송에 대한 직접적인 프롬프트 생성 경로는 없습니다. `call_handler`을 통해 전화하세요.

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "my_prompt",
    "content": "Hello, {{user_name}}!",
    "variables": [{"name": "user_name", "type": "string", "required": True}]
})
```

**입력_데이터**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name |
| `content` | `string` | Yes | Template body |
| `variables` | `list` | No | Variable definition. Both `["var1"]` format (old) and `[{"name": "var1", ...}]` format (new) are possible |

**반환 값**: `ok({"prompt": {...}})`

### 프롬프트 목록

**처리자**: `defaults.prompt.list`(`blocks/prompt/list.py`)

HTTP 전송에 대한 직접 프롬프트 목록 경로는 없습니다. `call_handler`을 통해 전화하세요.

```python
result = context["call_handler"]("defaults.prompt.list", {})
```

**입력_데이터**: `{}`(매개변수 없음)**반환 값**: `ok({"prompts": [...]})`

### 신속한 업데이트

**처리기**: `defaults.prompt.update`(`blocks/prompt/update.py`)**HTTP**: `PUT /api/prompts/{name}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name to be updated (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update |

`updates`에 가능한 필드: `content`(또는 `body`), `description`, `variables`, `metadata`, `name`(이름 변경). 이름을 바꾸면 오래된 파일이 삭제되고 색인이 자동으로 업데이트됩니다.

**반환 값**: `ok({"prompt": {...}})`

### 삭제 프롬프트

**처리기**: `defaults.prompt.delete`(`blocks/prompt/delete.py`)**HTTP**: `DELETE /api/prompts/{name}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Prompt name (auto-injected from URL path) |

**반환 값**: `ok({"deleted": "prompt_name"})`

### 신속한 렌더링

**처리자**: `defaults.prompt.render`(`blocks/prompt/render.py`)

HTTP 전송을 위한 직접 렌더링 경로는 없습니다. `call_handler`을 통해 전화하세요.

```python
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "a1b2c3d4",
    "variables": {"user_name": "Haru"}
})
```

**입력_데이터**:

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt_id` | `string` | No | Prompt ID. When specified, retrieved from PromptManager |
| `template` | `string` | No | Specify template string directly. `prompt_id` takes precedence |
| `variables` | `dict` | No | Variable value |

**반환 값**: `ok({"rendered": "rendered string", "prompt_id": "..." or null})`

### 시스템 프롬프트

**처리자**: `defaults.prompt.system`(`blocks/prompt/system.py`)

획득: `{"action": "get"}` → `ok({"content": "..."})`

설정: `{"action": "set", "content": "new system prompt"}` → `ok({"content": "..."})`

### 도구 ⇔ 프롬프트 변환

**처리기**: `defaults.prompt.convert`(`blocks/prompt/convert.py`)**HTTP**: `POST /api/prompts/convert`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `source_type` | `string` | Yes | `"tool"` or `"prompt"` |
| `source_name` | `string` | Yes | Source name |
| `target_type` | `string` | Yes | `"tool"` or `"prompt"` (must be different from source_type) |

**도구 → 프롬프트**: 도구의 `parameters`를 변수로, `summary`을 템플릿 본문 헤더로 변환합니다. `PromptTemplate.from_tool_schema()`이 사용됩니다.**프롬프트 → 도구**: 작성 경로로 유효하지 않습니다. `execution.type: "prompt"` 도구가 생성되지 않습니다. 필요한 경우 플로우/함수에서 `defaults.prompt.render`를 호출하고, 도구가 필요한 경우 `rumi_function` 또는 `capability` Facade로 별도로 정의합니다.

## 컨텍스트 가져오기의 예

```python
# プロンプトを作成（call_handler 経由）
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_aware",
    "content": "Messages so far: {{context.message_count}}\nConversation: {{context.conversation_id}}\n\nUser request: {{request}}",
    "variables": [{"name": "request", "type": "string", "required": True}]
})
```

렌더링 시 컨텍스트를 전달하면 `inject_context_variables()`은 `context.message_count` 및 `context.conversation_id`를 자동으로 삽입합니다.

## 구체적인 예

### 예시 1: 코드 검토 프롬프트

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

### 예시 2: 번역 프롬프트

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

### 예시 3: 상황 인식 요약 프롬프트

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_summary",
    "content": "Conversation has {{context.message_count}} messages ({{context.total_tokens}} tokens).\n\nPlease summarize the conversation so far, focusing on: {{focus}}\n\nMessages:\n{{context.messages}}",
    "variables": [
        {"name": "focus", "type": "string", "default": "key decisions and action items"}
    ]
})
```

## 모범 사례

`name`은 프롬프트의 목적을 명확하게 설명하는 이름이어야 합니다. 이렇게 하면 프롬프트 목록에서 해당 항목을 더 쉽게 식별할 수 있습니다.

`variables`에 `required: true`을 적절하게 설정해주세요. 필수 변수가 지정되지 않은 경우 `{{variable_name}}`가 출력에 남아 있습니다.

런타임에 컨텍스트 정보를 `content`(본문)에 자동으로 삽입하려면 `{{context.*}}` 변수를 사용하십시오. 사용자가 명시적으로 값을 지정하면 덮어쓰이지 않으므로 테스트 시 모의 값을 전달할 수 있습니다.

프롬프트에서 도구를 자동으로 생성하는 작성 경로가 잘못되었습니다. `context.*` 변수는 `defaults.prompt.resolve_for_conversation`에 의해 수동적으로 해결되며 도구가 필요한 경우 `rumi_function` / `capability` 외관으로 별도로 정의됩니다.

지속성 파일(`user_data/shared/prompts/`)은 `PromptManager`에서 관리됩니다. 파일명은 `_safe_filename(name) + ".json"`에 의해 생성되며, 영숫자, 하이픈, 밑줄 이외의 문자는 밑줄로 변환됩니다.
