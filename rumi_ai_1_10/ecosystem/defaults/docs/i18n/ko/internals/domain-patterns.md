<!-- docs-i18n-links:start -->
[EN](../../../internals/domain-patterns.md) | [JP](../../ja/internals/domain-patterns.md) | [KR](./domain-patterns.md) | [CN](../../zh-cn/internals/domain-patterns.md)
<!-- docs-i18n-links:end -->

# 도메인 레이어 디자인 패턴

기본 팩의 `domain/`에서 사용되는 디자인 패턴을 설명하십시오.

---

## 싱글톤 패턴

프로세스 전체에 걸쳐 인스턴스가 하나만 있고 모든 블록에서 공유되는 클래스에 사용됩니다. `__new__` 및 `_initialized` 플래그의 조합으로 구현됩니다.

### 구현 패턴

```python
class AIClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 初期化処理（1回だけ実行される）
```

### 적용 클래스

**AIClient** (`domain/ai_client/client.py`) — AI 공급자를 관리하고 위임합니다. 초기화 시 스텁 공급자를 등록하고, 환경 변수에서 감지된 공급자(OpenAI, Anthropic, Google)를 자동으로 등록합니다. `complete()`, `stream()`, `embed()`, `image_gen()`, `image_analyze()`, `transcribe()`, `tts()` 메서드가 있습니다. 모델 문자열 `"provider/model"`을 해결하고 해당 공급자에게 위임합니다.

**McpClient** (`domain/tool/mcp_client.py`) — MCP(모델 컨텍스트 프로토콜) 서버와의 연결을 관리합니다. `threading.Lock`을 사용하여 스레드로부터 안전한 서버 연결 관리를 수행합니다. `connect()`, `disconnect()`, `invoke()`, `list_servers()`, `get_server_tools()` 메서드가 있습니다.

**ToolRegistry** (`domain/tool/registry.py`) — 도구 정의를 등록하고 관리합니다. 메모리 내 dict + `user_data/shared/tools/`에 대한 지속성을 관리합니다. 시작 시 내장 도구(web_search, 계산기, file_reader)를 자동으로 등록하고 파일에서 동적 도구를 로드합니다. `threading.Lock`를 사용하여 스레드로부터 안전한 작동을 제공합니다.

**ChatStore** (`domain/chat/store.py`) — 대화 및 메시지의 메모리 내 관리 기능을 제공합니다. `__new__`에서 인스턴스를 공유하고 `_conversations`에서 dict를 유지합니다. CRUD 작업 외에도 `branch()`, `search()`, `export_conversation()`, `get_message_chain()` 등의 트리 작업을 제공합니다.

**Inspector** (`domain/dev/inspector.py`) — 요청 로그의 기록 및 검색을 관리합니다. `threading.Lock`으로 스레드 안전. 상한선은 `collections.deque(maxlen=1000)`에 의해 제어됩니다. `log_request()`, `get_log()`, `get_latest()`, `list_logs()`, `find_by_conversation()` 메서드가 있습니다.

---

## 매장 패턴

메모리 내 dict + 선택적 지속성을 사용하여 데이터를 관리하기 위한 패턴입니다. 싱글톤 패턴과 함께 사용됩니다.

### ChatStore 구현

ChatStore는 트리 구조의 메시지 관리를 제공합니다.

```python
class ChatStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conversations = {}
        return cls._instance
```

각 대화는 `_conversations[conversation_id]`에 저장되고 메시지는 `conv["messages"]` 목록에 보관됩니다. 메시지는 `parent_id` 및 `children_ids`으로 트리 구조를 형성합니다.

주요 작전: `create_conversation()`, `get_conversation()`, `list_conversations()`, `update_conversation()`, `delete_conversation()`, `add_message()`, `get_message()`, `update_message()`, `delete_message()`, `get_message_chain()`, `branch()`, `search()`, `export_conversation()`.

트리밍 작업: `get_messages_range()`, `delete_messages_bulk()`, `insert_message_at()`.

모든 공개 메서드는 `copy.deepcopy()`을 사용하여 반환 값을 복제합니다(참조에 의한 의도하지 않은 수정 방지).

### 인스펙터 구현

Inspector는 `collections.deque(maxlen=1000)` + `dict` 인덱스를 사용하여 로그를 관리합니다.

```python
class Inspector:
    _instance = None
    _lock = threading.Lock()
    MAX_LOGS = 1000

    def __init__(self):
        self._logs: deque = deque(maxlen=self.MAX_LOGS)
        self._index: dict[str, dict] = {}
        self._data_lock = threading.Lock()
```

deque의 maxlen을 초과하면 이전 항목이 자동으로 삭제되는 동시에 `_index`에서도 삭제됩니다.

---

## 공급자 패턴

`BaseProvider` 추상 기본 클래스에서 상속하고 각 AI 공급자의 API 차이점을 흡수하는 패턴입니다.

### 기본 공급자(`domain/ai_client/base_provider.py`)

```python
class BaseProvider:
    def complete(self, model, messages, tools, params):
        raise NotImplementedError

    def stream(self, model, messages, tools, params):
        raise NotImplementedError

    def embed(self, model, input_text):
        raise NotImplementedError

    def image_gen(self, model, prompt, params):
        raise NotImplementedError

    def image_analyze(self, model, image, prompt):
        raise NotImplementedError

    def transcribe(self, model, audio, params):
        raise NotImplementedError

    def tts(self, model, text, voice):
        raise NotImplementedError

    def build_request(self, messages):
        return messages

    def parse_response(self, raw):
        return raw
```

### 구현 공급자

**StubProvider** — 고정된 응답을 반환합니다. 테스트 및 개발용. API 호출이 없습니다.

**OpenAIProvider** — OpenAI API를 호출합니다. 환경 변수 `OPENAI_API_KEY`에 의해 감지되었습니다.

**AnthropicProvider** — Anthropic API를 호출합니다. 환경 변수 `ANTHROPIC_API_KEY`에 의해 감지되었습니다.

**GoogleProvider** — Google AI API를 호출합니다. 환경 변수 `GOOGLE_API_KEY`에 의해 감지되었습니다.

**RumiProvider** — 메타 공급자. 파이프라인을 통해 요청을 처리하거나 대체 공급자에게 위임하세요. AIClient 인스턴스를 수신하고 하나 이상의 다른 공급자가 등록된 경우에만 활성화됩니다.

### 공급자 자동 감지

`domain/ai_client/providers/__init__.py`의 `detect_available_providers()`은 환경 변수를 확인하고 자동으로 API 키 세트를 사용하여 공급자를 인스턴스화하고 반환합니다. AIClient의 `__init__` 내에서 호출됩니다.

---

## 빌더 패턴

### ToolBuilder(`domain/tool/builder.py`)

ToolBuilder는 AI를 사용하여 도구에 대한 핸들러 코드를 생성하는 도우미입니다.

**generate_skeleton(name, 설명, 매개변수)** — JSON 스키마에서 핸들러 코드 뼈대를 생성합니다. AI 제공자를 사용할 수 없는 경우 대체합니다.

```python
skeleton = generate_skeleton("my_tool", "ツールの説明", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"]
})
```

**generate_handler_code_with_ai(이름, 설명, 매개변수, 모델=없음)** — AI를 사용하여 완전한 핸들러 코드를 생성합니다. 모델이 없음인 경우 첫 번째로 사용 가능한 스텁이 아닌 공급자를 사용하세요. AI 출력이 유효하지 않은 경우 스켈레톤으로 대체됩니다.

---

## 템플릿 패턴

### 프롬프트 템플릿(`domain/prompt/template.py`)

도구 및 프롬프트를 위한 통합 템플릿 시스템입니다. 둘 다 비슷한 구조(이름/설명 + 매개변수/변수 + 실행 로직/본문)를 가지고 있습니다.

**변수 확장 구문:**

```
{{variable_name}}           — 通常変数（ユーザー指定）
{{context.total_tokens}}    — 特殊変数（実行時に自動注入）
{{context.message_count}}   — 特殊変数
{{context.messages}}        — 特殊変数
{{context.system_prompt}}   — 特殊変数
{{context.conversation_id}} — 特殊変数
```

**주요 방법:**

`to_dict()` / `from_dict()` — 직렬화/역직렬화.

`to_tool_schema()` — 도구의 JSON 스키마 형식으로 변환합니다. `context.*` 도구 매개변수에 변수를 포함하지 마세요.

`from_tool_schema()` — 도구 정의에서 PromptTemplate을 생성합니다.

`extract_variable_names()` — 본문의 `{{...}}`에서 변수 이름을 추출합니다.

`list_context_variables()` — `context.*` 변수만 반환합니다.

`list_user_variables()` — `context.*`이 아닌 변수만 반환합니다.

### 프롬프트 관리자(`domain/prompt/manager.py`)

PromptManager는 메모리 내 dict + `user_data/shared/prompts/`에 대한 JSON 파일 지속성을 사용하여 프롬프트를 관리합니다. `get_manager()`을 사용하여 모듈 수준 싱글톤으로 얻습니다.

**주요 방법:** `create_prompt()`, `get_prompt()`, `get_prompt_by_name()`, `list_prompts()`, `update_prompt()`, `delete_prompt()`, `to_template()`, `create_from_template()`, `get_system_prompt()`, `set_system_prompt()`.

**컨텍스트 변수 주입:** `inject_context_variables(variables, context)` 정적 메서드는 컨텍스트 딕셔너리에서 `context.total_tokens`, `context.message_count`와 같은 특수 변수를 자동으로 주입합니다.
