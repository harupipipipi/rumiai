<!-- docs-i18n-links:start -->
[EN](../../writing-prompts.md) | [JP](../ja/writing-prompts.md) | [KR](./writing-prompts.md) | [CN](../zh-cn/writing-prompts.md)
<!-- docs-i18n-links:end -->

# 프롬프트 작성

기본 팩을 사용하여 프롬프트 템플릿을 생성하고 관리하기 위한 가이드입니다. 핸들러는 `blocks/prompt/`에서 구현되며 도메인 로직은 `domain/prompt/manager.py`(PromptManager), `domain/prompt/template.py`(PromptTemplate) 및 `domain/prompt/renderer.py`(렌더링)에서 구현됩니다.

## 프롬프트 컨셉

프롬프트는 템플릿 변수를 포함하는 재사용 가능한 텍스트 템플릿입니다. `{{variable_name}}` 구문으로 변수를 삽입하고 렌더링 시 실제 값으로 대체합니다.

프롬프트는 메모리 내 dict + `user_data/shared/prompts/`에 대한 JSON 파일 지속성을 갖춘 `PromptManager`(싱글톤)에 의해 관리됩니다. 시작 시 JSON 파일에서 자동 로드됩니다.

프롬프트와 도구는 `PromptTemplate`를 통해 상호 교환 가능합니다. `blocks/prompt/convert.py`을 사용하면 도구 → 프롬프트, 프롬프트 → 도구로 변환할 수 있습니다.

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

지속형 JSON 형식은 다음과 같습니다(`domain/prompt/manager.py`의 `create_prompt()`).

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

| 필드 | 유형 | 설명 |
|---|---|---|
| §루미§0§ | §루미§1§ | 자동으로 생성된 8자리 16진수 ID |
| §루미§0§ | §루미§1§ | 프롬프트 이름(고유) |
| §루미§0§ | §루미§1§ | 템플릿 본문(`body`의 별칭. 이전 버전과의 호환성을 위해 둘 다 유지) |
| §루미§0§ | §루미§1§ | 템플릿 본문 |
| §루미§0§ | §루미§1§ | 설명 |
| §루미§0§ | §루미§1§ | 변수 정의 목록 |
| §루미§0§ | §루미§1§ | 자유 형식 메타데이터 |
| §루미§0§ | §루미§1§ | 생성 날짜 및 시간(ISO 8601) |
| §루미§0§ | §루미§1§ | 업데이트된 날짜 및 시간(ISO 8601) |

변수의 각 요소에는 다음과 같은 필드가 있습니다.

| 필드 | 유형 | 설명 |
|---|---|---|
| §루미§0§ | §루미§1§ | 변수 이름 |
| §루미§0§ | §루미§1§ | 유형(`"string"`, `"integer"` 등). 기본 `"string"` |
| §루미§0§ | §루미§1§ | 기본값. `null`에는 없음 |
| §루미§0§ | §루미§1§ | 필수인가요? 기본 `false` |

이전 형식(`variables: ["var1", "var2"]`)도 지원되며 `_normalize_variables()`에서 새 형식으로 자동 변환됩니다.

## 템플릿 변수

### 일반 변수

`{{variable_name}}`에 설명되어 있습니다. 렌더링 중에 `variables` dict의 값으로 대체되었습니다. `domain/prompt/renderer.py`의 `render()` 기능은 `_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")`를 사용하여 한 번에 대체합니다.

존재하지 않는 변수는 그대로 유지됩니다(오류가 발생하지 않음). 공백이 허용됩니다(`{{ name }}`도 유효함).

### 특수 변수(컨텍스트 변수)

`domain/prompt/template.py`에 정의된 `CONTEXT_VARIABLE_KEYS`.

| 변수 이름 | 유형 | 설명 |
|---|---|---|
| §루미§0§ | §루미§1§ | 현재 컨텍스트의 총 토큰 수 |
| §루미§0§ | §루미§1§ | 메시지 수 |
| §루미§0§ | §루미§1§ | 메시지 내용. 목록/딕셔너리의 경우 JSON 문자열 |
| §루미§0§ | §루미§1§ | 시스템 프롬프트 |
| §루미§0§ | §루미§1§ | 대화 ID |

특수 변수는 `PromptManager.inject_context_variables(variables, context)`로 자동 주입됩니다. 사용자가 명시적으로 지정한 값은 덮어쓰이지 않습니다. 값은 컨텍스트 dict(`total_tokens`, `message_count` 등)의 해당 키에서 검색됩니다.

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

HTTP 전송에 대한 직접적인 프롬프트 생성 경로는 없습니다. `call_handler`를 통해 전화하세요.

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "my_prompt",
    "content": "Hello, {{user_name}}!",
    "variables": [{"name": "user_name", "type": "string", "required": True}]
})
```

**입력_데이터**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | 예 | 프롬프트 이름 |
| §루미§0§ | §루미§1§ | 예 | 템플릿 본문 |
| §루미§0§ | §루미§1§ | 아니요 | 변수 정의. `["var1"]` 형식(기존)과 `[{"name": "var1", ...}]` 형식(신규) 모두 가능 |

**반환 값**: `ok({"prompt": {...}})`

### 프롬프트 목록

**처리자**: `defaults.prompt.list`(`blocks/prompt/list.py`)

HTTP 전송에 대한 직접 프롬프트 목록 경로는 없습니다. `call_handler`를 통해 전화하세요.

```python
result = context["call_handler"]("defaults.prompt.list", {})
```

**input_data**: `{}`(매개변수 없음)

**반환 값**: `ok({"prompts": [...]})`

### 신속한 업데이트

**처리자**: `defaults.prompt.update`(`blocks/prompt/update.py`)

**HTTP**: §루미§0§

**입력_데이터**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | 예 | 업데이트할 프롬프트 이름(URL 경로에서 자동으로 삽입) |
| §루미§0§ | §루미§1§ | 예 | 업데이트할 필드 |

`updates`에 가능한 필드: `content`(또는 `body`), `description`, `variables`, `metadata`, `name`(이름 변경). 이름을 바꾸면 오래된 파일이 삭제되고 색인이 자동으로 업데이트됩니다.

**반환 값**: `ok({"prompt": {...}})`

### 삭제 프롬프트

**처리자**: `defaults.prompt.delete`(`blocks/prompt/delete.py`)

**HTTP**: §루미§0§

**입력_데이터**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | 예 | 프롬프트 이름(URL 경로에서 자동 삽입) |

**반환 값**: `ok({"deleted": "prompt_name"})`

### 신속한 렌더링

**처리자**: `defaults.prompt.render`(`blocks/prompt/render.py`)

HTTP 전송을 위한 직접 렌더링 경로는 없습니다. `call_handler`를 통해 전화하세요.

```python
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "a1b2c3d4",
    "variables": {"user_name": "Haru"}
})
```

**입력_데이터**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | 아니요 | 프롬프트 ID. 지정된 경우 PromptManager |
| §루미§0§ | §루미§1§ | 아니요 | 템플릿 문자열을 직접 지정합니다. `prompt_id`가 우선 적용됩니다 |
| §루미§0§ | §루미§1§ | 아니요 | 변수값 |

**반환 값**: `ok({"rendered": "rendered string", "prompt_id": "..." or null})`

### 시스템 프롬프트

**처리자**: `defaults.prompt.system`(`blocks/prompt/system.py`)

획득: `{"action": "get"}` → `ok({"content": "..."})`

설정: `{"action": "set", "content": "new system prompt"}` → `ok({"content": "..."})`

### 도구 ⇔ 프롬프트 변환

**처리자**: `defaults.prompt.convert`(`blocks/prompt/convert.py`)

**HTTP**: §루미§0§

**입력_데이터**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | 예 | `"tool"` 또는 `"prompt"` |
| §루미§0§ | §루미§1§ | 예 | 소스 이름 |
| §루미§0§ | §루미§1§ | 예 | `"tool"` 또는 `"prompt"`(source_type과 달라야 함) |

**도구 → 프롬프트**: 도구의 `parameters`를 변수로 변환하고 `summary`을 템플릿 본문 헤더로 변환합니다. `PromptTemplate.from_tool_schema()`가 사용됩니다.

**프롬프트 → 도구**: 템플릿 변수를 `parameters`로, 본문을 `execution.body`로 변환합니다. `PromptTemplate.to_tool_schema()`는 `execution.type: "prompt"`의 도구로 `ToolRegistry.register_dynamic()`에 사용되고 등록되어 있습니다. context.* 변수는 도구 매개변수에서 제외됩니다.

## 컨텍스트 가져오기의 예

```python
# プロンプトを作成（call_handler 経由）
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_aware",
    "content": "Messages so far: {{context.message_count}}\nConversation: {{context.conversation_id}}\n\nUser request: {{request}}",
    "variables": [{"name": "request", "type": "string", "required": True}]
})
```

렌더링 시 컨텍스트를 전달하면 `inject_context_variables()`는 `context.message_count` 및 `context.conversation_id`를 자동 주입합니다.

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

`variables`에 `required: true`를 적절하게 설정해 주세요. 필수 변수가 지정되지 않은 경우 `{{variable_name}}`가 출력에 남아 있습니다.

`{{context.*}}` 변수를 사용하면 런타임 시 컨텍스트 정보를 `content`(본문)에 자동으로 주입할 수 있습니다. 사용자가 명시적으로 값을 지정하면 덮어쓰이지 않으므로 테스트 시 모의 값을 전달할 수 있습니다.

프롬프트에서 도구로 변환(`prompt → tool`)에서는 `context.*` 변수가 도구 매개변수에서 자동으로 제외됩니다. 이는 컨텍스트 변수가 런타임에 자동으로 삽입될 것으로 예상되기 때문입니다.

지속성 파일(`user_data/shared/prompts/`)은 `PromptManager`에 의해 관리됩니다. 파일 이름은 `_safe_filename(name) + ".json"`에 의해 생성되며, 영숫자, 하이픈, 밑줄 이외의 문자는 밑줄로 변환됩니다.
