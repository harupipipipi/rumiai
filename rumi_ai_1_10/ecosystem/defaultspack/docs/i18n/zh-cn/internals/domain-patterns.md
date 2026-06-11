<!-- docs-i18n-links:start -->
[EN](../../../internals/domain-patterns.md) | [JP](../../ja/internals/domain-patterns.md) | [KR](../../ko/internals/domain-patterns.md) | [CN](./domain-patterns.md)
<!-- docs-i18n-links:end -->

# 领域层设计模式

解释默认包`domain/`下使用的设计模式。

---

## 单例模式

用于在整个过程中只有一个实例并由所有块共享的类。由`__new__`和`_initialized`标志的组合实现。

### 实现模式

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

### 适用类别

**AIClient** (`domain/ai_client/client.py`) — 管理和委托人工智能提供商。在初始化期间注册存根提供程序，并自动注册在环境变量中检测到的提供程序（OpenAI、Anthropic、Google）。具有`complete()`、`stream()`、`embed()`、`image_gen()`、`image_analyze()`、`transcribe()`、`tts()`方法。解析模型字符串`"provider/model"`并委托给相应的提供者。**McpClient** (`domain/tool/mcp_client.py`) — 管理与 MCP（模型上下文协议）服务器的连接。使用`threading.Lock`执行线程安全的服务器连接管理。具有`connect()`、`disconnect()`、`invoke()`、`list_servers()`、`get_server_tools()`方法。**ToolRegistry** (`domain/tool/registry.py`) — 注册和管理工具定义。管理内存中字典的持久性 + `user_data/shared/tools/`。启动时自动注册内置工具（web_search、calculator、file_reader），并从文件中加载动态工具。使用`threading.Lock`提供线程安全操作。**ChatStore** (`domain/chat/store.py`) — 提供对话和消息的内存管理。在`__new__`中共享实例并在`_conversations`中维护字典。除了CRUD操作外，它还提供`branch()`、`search()`、`export_conversation()`、`get_message_chain()`等树操作。**检查器** (`domain/dev/inspector.py`) — 管理请求日志的记录和检索。使用`threading.Lock`实现线程安全。上限由`collections.deque(maxlen=1000)`控制。具有`log_request()`、`get_log()`、`get_latest()`、`list_logs()`、`find_by_conversation()`方法。

---

## 存储模式

一种使用内存字典+可选持久性来管理数据的模式。与单例模式结合使用。

### ChatStore 实施

ChatStore提供树形结构的消息管理：

```python
class ChatStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conversations = {}
        return cls._instance
```

每个对话都存储在`_conversations[conversation_id]`中，消息保存在`conv["messages"]`列表中。该消息由`parent_id`和`children_ids`构成树形结构。

主要经营：`create_conversation()`，`get_conversation()`，`list_conversations()`，`update_conversation()`，`delete_conversation()`，`add_message()`，`get_message()`，`update_message()`，`delete_message()`，`get_message_chain()`，`branch()`，`search()`，`export_conversation()`。

修剪操作：`get_messages_range()`、`delete_messages_bulk()`、`insert_message_at()`。

所有公共方法都使用`copy.deepcopy()`重复返回值（防止通过引用无意修改）。

### 检查器实施

Inspector 使用 `collections.deque(maxlen=1000)` + `dict` 索引管理日志：

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

当超过双端队列的 maxlen 时，旧条目将被自动删除，同时也会从`_index` 中删除。

---

## 提供者模式

`BaseProvider` 一种从抽象基类继承并吸收每个 AI 提供商的 API 差异的模式。

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

### 实施提供商

**StubProvider** — 返回固定响应。用于测试和开发。没有 API 调用。**OpenAIProvider** — 调用 OpenAI API。通过环境变量`OPENAI_API_KEY`检测。**AnthropicProvider** — 调用 Anthropic API。通过环境变量`ANTHROPIC_API_KEY`检测。**GoogleProvider** — 调用 Google AI API。通过环境变量`GOOGLE_API_KEY`检测。**RumiProvider** — 元提供商。通过 Pipeline 处理请求或委托给后备提供商。接收 AIClient 实例，并且仅在注册了一个或多个其他提供程序时才启用。

### 提供商自动检测

`domain/ai_client/providers/__init__.py` 中的`detect_available_providers()` 检查环境变量并自动实例化并返回具有 API 密钥集的提供程序。在 AIClient 的 `__init__` 内调用。

---

## 构建器模式

### 工具生成器 (`domain/tool/builder.py`)

ToolBuilder 是一个使用 AI 为工具生成处理程序代码的助手。

**generate_骨骼(名称、描述、参数)** — 从 JSON 模式生成处理程序代码框架。如果 AI 提供商不可用，则进行回退。

```python
skeleton = generate_skeleton("my_tool", "ツールの説明", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"]
})
```

**generate_handler_code_with_ai(name、description、parameters、model=None)** — 使用 AI 生成完整的处理程序代码。如果 model 为 None，则使用第一个可用的非存根提供程序。如果AI输出无效则回退到骨骼。

---

## 模板模式

### 提示模板 (`domain/prompt/template.py`)

被动提示模板表达。提示不会移动工具/提供者/权限，并将渲染的文本返回到流程/功能。

**变量扩展语法：**

```
{{variable_name}}           — 通常変数（ユーザー指定）
{{context.total_tokens}}    — 特殊変数（実行時に自動注入）
{{context.message_count}}   — 特殊変数
{{context.messages}}        — 特殊変数
{{context.system_prompt}}   — 特殊変数
{{context.conversation_id}} — 特殊変数
```

**主要方法：**

`to_dict()` / `from_dict()` — 序列化/反序列化。

`to_tool_schema()` — 返回兼容 UI 的函数外观草稿。提示工具未注册为创作路径。

`from_tool_schema()` — 从工具定义生成提示模板。

`extract_variable_names()` — 从正文中的`{{...}}` 中提取变量名称。

`list_context_variables()` — `context.*` 仅返回变量。

`list_user_variables()` — 仅返回非`context.*` 变量。

### 提示管理器 (`domain/prompt/manager.py`)

PromptManager 通过将 JSON 文件持久化到内存中的字典 + `user_data/shared/prompts/` 来管理提示。通过`get_manager()` 作为模块级单例获得。

**关键方法：**`create_prompt()`、`get_prompt()`、`get_prompt_by_name()`、`list_prompts()`、`update_prompt()`、`delete_prompt()`、`to_template()`、`create_from_template()`、`get_system_prompt()`、`set_system_prompt()`。**上下文变量注入：**`inject_context_variables(variables, context)`静态方法自动从上下文字典中注入特殊变量，例如`context.total_tokens`，`context.message_count`。
