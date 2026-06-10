<!-- docs-i18n-links:start -->
[EN](./domain-patterns.md) | [JP](../i18n/ja/internals/domain-patterns.md) | [KR](../i18n/ko/internals/domain-patterns.md) | [CN](../i18n/zh-cn/internals/domain-patterns.md)
<!-- docs-i18n-links:end -->

# Domain layer design pattern

Explain the design patterns used under `domain/` of defaults pack.

---

## Singleton pattern

Used for classes that only have one instance throughout the process and are shared by all blocks. Implemented by a combination of `__new__` and `_initialized` flags.

### Implementation pattern

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

### Applicable class

**AIClient** (`domain/ai_client/client.py`) — Manage and delegate AI providers. Register the stub provider during initialization and automatically register the providers (OpenAI, Anthropic, Google) detected in the environment variables. Has `complete()`, `stream()`, `embed()`, `image_gen()`, `image_analyze()`, `transcribe()`, `tts()` methods. Resolve model string `"provider/model"` and delegate to corresponding provider.

**McpClient** (`domain/tool/mcp_client.py`) — Manages connections with MCP (Model Context Protocol) servers. Perform thread-safe server connection management with `threading.Lock`. Has `connect()`, `disconnect()`, `invoke()`, `list_servers()`, `get_server_tools()` methods.

**ToolRegistry** (`domain/tool/registry.py`) — Register and manage tool definitions. Manage persistence to in-memory dict + `user_data/shared/tools/`. Automatically registers built-in tools (web_search, calculator, file_reader) at startup, and loads dynamic tools from files. Provide thread-safe operation with `threading.Lock`.

**ChatStore** (`domain/chat/store.py`) — Provides in-memory management of conversations and messages. Share instances in `__new__` and maintain dict in `_conversations`. In addition to CRUD operations, it provides tree operations such as `branch()`, `search()`, `export_conversation()`, `get_message_chain()`.

**Inspector** (`domain/dev/inspector.py`) — Manages recording and retrieval of request logs. Thread safe with `threading.Lock`. The upper limit is controlled by `collections.deque(maxlen=1000)`. Has `log_request()`, `get_log()`, `get_latest()`, `list_logs()`, `find_by_conversation()` methods.

---

## Store pattern

A pattern for managing data with an in-memory dict + optional persistence. Used in conjunction with singleton pattern.

### ChatStore implementation

ChatStore provides tree-structured message management:

```python
class ChatStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conversations = {}
        return cls._instance
```

Each conversation is stored in `_conversations[conversation_id]` and messages are kept in a `conv["messages"]` list. The message forms a tree structure with `parent_id` and `children_ids`.

Main operations: `create_conversation()`, `get_conversation()`, `list_conversations()`, `update_conversation()`, `delete_conversation()`, `add_message()`, `get_message()`, `update_message()`, `delete_message()`, `get_message_chain()`, `branch()`, `search()`, `export_conversation()`.

Trimming operations: `get_messages_range()`, `delete_messages_bulk()`, `insert_message_at()`.

All public methods duplicate return values ​​with `copy.deepcopy()` (preventing unintentional modification by reference).

### Inspector implementation

Inspector manages logs with `collections.deque(maxlen=1000)` + `dict` index:

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

When the deque's maxlen is exceeded, old entries are automatically deleted and also deleted from `_index` at the same time.

---

## Provider pattern

`BaseProvider` A pattern that inherits from an abstract base class and absorbs API differences from each AI provider.

### BaseProvider (`domain/ai_client/base_provider.py`)

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

### Implementation provider

**StubProvider** — Returns a fixed response. For testing and development. No API calls.

**OpenAIProvider** — Call the OpenAI API. Detected by environment variable `OPENAI_API_KEY`.

**AnthropicProvider** — Calls the Anthropic API. Detected by environment variable `ANTHROPIC_API_KEY`.

**GoogleProvider** — Calls Google AI API. Detected by environment variable `GOOGLE_API_KEY`.

**RumiProvider** — Meta provider. Process the request via Pipeline or delegate to a fallback provider. Receives an AIClient instance and is only enabled if one or more other providers are registered.

### Provider auto-detection

`detect_available_providers()` in `domain/ai_client/providers/__init__.py` checks the environment variables and automatically instantiates and returns the provider with the API key set. Called within `__init__` of AIClient.

---

## Builder pattern

### ToolBuilder (`domain/tool/builder.py`)

ToolBuilder is a helper that uses AI to generate handler code for tools.

**generate_skeleton(name, description, parameters)** — Generate handler code skeleton from JSON Schema. Fallback if AI provider is unavailable.

```python
skeleton = generate_skeleton("my_tool", "ツールの説明", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"]
})
```

**generate_handler_code_with_ai(name, description, parameters, model=None)** — Generate complete handler code using AI. If model is None, use the first available non-stub provider. Fallback to skeleton if AI output is invalid.

---

## Template pattern

### PromptTemplate (`domain/prompt/template.py`)

A unified template system for tools and prompts. Both have similar structures (name/description + parameters/variables + execution logic/body).

**Variable expansion syntax:**

```
{{variable_name}}           — 通常変数（ユーザー指定）
{{context.total_tokens}}    — 特殊変数（実行時に自動注入）
{{context.message_count}}   — 特殊変数
{{context.messages}}        — 特殊変数
{{context.system_prompt}}   — 特殊変数
{{context.conversation_id}} — 特殊変数
```

**Main method:**

`to_dict()` / `from_dict()` — Serialization/Deserialization.

`to_tool_schema()` — Convert to tool's JSON Schema format. `context.*` Do not include variables in tool parameters.

`from_tool_schema()` — Generate PromptTemplate from tool definition.

`extract_variable_names()` — Extract variable name from `{{...}}` in body.

`list_context_variables()` — `context.*` Return variables only.

`list_user_variables()` — Return only non-`context.*` variables.

### PromptManager (`domain/prompt/manager.py`)

PromptManager manages prompts with JSON file persistence to an in-memory dict + `user_data/shared/prompts/`. Obtained as a module-level singleton with `get_manager()`.

**Key methods:** `create_prompt()`, `get_prompt()`, `get_prompt_by_name()`, `list_prompts()`, `update_prompt()`, `delete_prompt()`, `to_template()`, `create_from_template()`, `get_system_prompt()`, `set_system_prompt()`.

**Context variable injection:** `inject_context_variables(variables, context)` Static method automatically injects special variables such as `context.total_tokens`, `context.message_count` from the context dict.
