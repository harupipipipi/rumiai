# Domain 層デザインパターン

defaults Pack の `domain/` 配下で使用されるデザインパターンを解説する。

---

## シングルトンパターン

プロセス全体で 1 つのインスタンスのみを保持し、すべての block から共有されるクラスに使用される。`__new__` と `_initialized` フラグの組み合わせで実装される。

### 実装パターン

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

### 適用クラス

**AIClient** (`domain/ai_client/client.py`) — AI プロバイダーの管理と委譲を行う。初期化時に stub プロバイダーを登録し、環境変数で検出されたプロバイダー（OpenAI, Anthropic, Google）を自動登録する。`complete()`, `stream()`, `embed()`, `image_gen()`, `image_analyze()`, `transcribe()`, `tts()` メソッドを持つ。モデル文字列 `"provider/model"` を解決して対応するプロバイダーに委譲する。

**McpClient** (`domain/tool/mcp_client.py`) — MCP (Model Context Protocol) サーバーとの接続を管理する。`threading.Lock` によるスレッドセーフなサーバー接続管理を行う。`connect()`, `disconnect()`, `invoke()`, `list_servers()`, `get_server_tools()` メソッドを持つ。

**ToolRegistry** (`domain/tool/registry.py`) — ツール定義の登録・管理を行う。インメモリ dict + `user_data/shared/tools/` への永続化を管理する。起動時にビルトインツール（web_search, calculator, file_reader）を自動登録し、動的ツールをファイルから読み込む。`threading.Lock` によるスレッドセーフな操作を提供する。

**ChatStore** (`domain/chat/store.py`) — 会話とメッセージのインメモリ管理を行う。`__new__` でインスタンスを共有し、`_conversations` dict を保持する。CRUD 操作に加え、`branch()`, `search()`, `export_conversation()`, `get_message_chain()` などのツリー操作を提供する。

**Inspector** (`domain/dev/inspector.py`) — リクエストログの記録と取得を管理する。`threading.Lock` でスレッドセーフ。`collections.deque(maxlen=1000)` で上限管理される。`log_request()`, `get_log()`, `get_latest()`, `list_logs()`, `find_by_conversation()` メソッドを持つ。

---

## ストアパターン

インメモリ dict + オプショナルな永続化でデータを管理するパターン。シングルトンパターンと組み合わせて使用される。

### ChatStore の実装

ChatStore はツリー構造のメッセージ管理を提供する:

```python
class ChatStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conversations = {}
        return cls._instance
```

各会話は `_conversations[conversation_id]` に格納され、メッセージは `conv["messages"]` リストに保持される。メッセージは `parent_id` と `children_ids` で木構造を形成する。

主な操作: `create_conversation()`, `get_conversation()`, `list_conversations()`, `update_conversation()`, `delete_conversation()`, `add_message()`, `get_message()`, `update_message()`, `delete_message()`, `get_message_chain()`, `branch()`, `search()`, `export_conversation()`。

トリミング用操作: `get_messages_range()`, `delete_messages_bulk()`, `insert_message_at()`。

すべての公開メソッドは `copy.deepcopy()` で返却値を複製する（参照による意図しない変更を防ぐ）。

### Inspector の実装

Inspector は `collections.deque(maxlen=1000)` + `dict` インデックスでログを管理する:

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

deque の maxlen を超えると古いエントリが自動削除され、同時に `_index` からも削除される。

---

## プロバイダーパターン

`BaseProvider` 抽象基底クラスを継承して、各 AI プロバイダーの API 差分を吸収するパターン。

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

### 実装プロバイダー

**StubProvider** — 固定レスポンスを返す。テスト・開発用。API 呼び出しなし。

**OpenAIProvider** — OpenAI API を呼び出す。環境変数 `OPENAI_API_KEY` で検出。

**AnthropicProvider** — Anthropic API を呼び出す。環境変数 `ANTHROPIC_API_KEY` で検出。

**GoogleProvider** — Google AI API を呼び出す。環境変数 `GOOGLE_API_KEY` で検出。

**RumiProvider** — メタプロバイダー。Pipeline 経由でリクエストを処理するか、フォールバックプロバイダーに委譲する。AIClient インスタンスを受け取り、他のプロバイダーが 1 つ以上登録されている場合のみ有効化される。

### プロバイダーの自動検出

`domain/ai_client/providers/__init__.py` の `detect_available_providers()` が環境変数をチェックし、API キーが設定されているプロバイダーを自動的にインスタンス化して返す。AIClient の `__init__` 内で呼び出される。

---

## Builder パターン

### ToolBuilder (`domain/tool/builder.py`)

ToolBuilder は AI を使ってツールのハンドラコードを生成するヘルパーである。

**generate_skeleton(name, description, parameters)** — JSON Schema からハンドラコードのスケルトンを生成する。AI プロバイダーが利用できない場合のフォールバック。

```python
skeleton = generate_skeleton("my_tool", "ツールの説明", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"]
})
```

**generate_handler_code_with_ai(name, description, parameters, model=None)** — AI を使って完全なハンドラコードを生成する。model が None の場合は利用可能な最初の非 stub プロバイダーを使用する。AI の出力が不正な場合はスケルトンにフォールバックする。

---

## テンプレートパターン

### PromptTemplate (`domain/prompt/template.py`)

tool と prompt の統一テンプレートシステム。両者は構造が類似している（name/description + parameters/variables + 実行ロジック/本文）。

**変数展開構文:**

```
{{variable_name}}           — 通常変数（ユーザー指定）
{{context.total_tokens}}    — 特殊変数（実行時に自動注入）
{{context.message_count}}   — 特殊変数
{{context.messages}}        — 特殊変数
{{context.system_prompt}}   — 特殊変数
{{context.conversation_id}} — 特殊変数
```

**主要メソッド:**

`to_dict()` / `from_dict()` — シリアライズ/デシリアライズ。

`to_tool_schema()` — tool の JSON Schema 形式に変換。`context.*` 変数はツールパラメータに含めない。

`from_tool_schema()` — tool 定義から PromptTemplate を生成。

`extract_variable_names()` — body 内の `{{...}}` から変数名を抽出。

`list_context_variables()` — `context.*` 変数のみを返す。

`list_user_variables()` — 非 `context.*` 変数のみを返す。

### PromptManager (`domain/prompt/manager.py`)

PromptManager はインメモリ dict + `user_data/shared/prompts/` への JSON ファイル永続化でプロンプトを管理する。モジュールレベルのシングルトンとして `get_manager()` で取得する。

**主要メソッド:** `create_prompt()`, `get_prompt()`, `get_prompt_by_name()`, `list_prompts()`, `update_prompt()`, `delete_prompt()`, `to_template()`, `create_from_template()`, `get_system_prompt()`, `set_system_prompt()`。

**コンテキスト変数注入:** `inject_context_variables(variables, context)` 静的メソッドが、context dict から `context.total_tokens`, `context.message_count` 等の特殊変数を自動注入する。
