<!-- docs-i18n-links:start -->
[EN](../../../internals/domain-patterns.md) | [JP](./domain-patterns.md) | [KR](../../ko/internals/domain-patterns.md) | [CN](../../zh-cn/internals/domain-patterns.md)
<!-- docs-i18n-links:end -->

# ドメイン層の設計パターン

デフォルト パックの `domain/` で使用されるデザイン パターンについて説明します。

---

## シングルトン パターン

プロセス全体でインスタンスが 1 つだけあり、すべてのブロックで共有されるクラスに使用されます。 `__new__` フラグと `_initialized` フラグの組み合わせによって実装されます。

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

### 対象クラス

**AIClient** (`domain/ai_client/client.py`) — AI プロバイダーを管理および委任します。初期化時にスタブプロバイダを登録し、検出されたプロバイダ（OpenAI、Anthropic、Google）を環境変数に自動登録します。 `complete()`、`stream()`、`embed()`、`image_gen()`、`image_analyze()`、`transcribe()`、`tts()`メソッドがあります。モデル文字列 `"provider/model"` を解決し、対応するプロバイダーに委任します。**McpClient** (`domain/tool/mcp_client.py`) — MCP (Model Context Protocol) サーバーとの接続を管理します。 `threading.Lock` を使用して、スレッドセーフなサーバー接続管理を実行します。 `connect()`、`disconnect()`、`invoke()`、`list_servers()`、`get_server_tools()`のメソッドがあります。**ToolRegistry** (`domain/tool/registry.py`) — ツール定義を登録および管理します。メモリ内辞書 + `user_data/shared/tools/` への永続性を管理します。起動時に組み込みツール (web_search、calculator、file_reader) を自動的に登録し、ファイルから動的ツールを読み込みます。 `threading.Lock` を使用してスレッドセーフな操作を提供します。**ChatStore** (`domain/chat/store.py`) — 会話とメッセージのメモリ内管理を提供します。 `__new__` でインスタンスを共有し、`_conversations` で辞書を維持します。 CRUD 操作に加えて、`branch()`、`search()`、`export_conversation()`、`get_message_chain()` などのツリー操作も提供します。**インスペクター** (`domain/dev/inspector.py`) — リクエスト ログの記録と取得を管理します。 `threading.Lock` によるスレッドセーフ。上限は`collections.deque(maxlen=1000)`によって制御されます。 `log_request()`、`get_log()`、`get_latest()`、`list_logs()`、`find_by_conversation()`のメソッドがあります。

---

## ストアパターン

インメモリ辞書とオプションの永続性を使用してデータを管理するパターン。シングルトン パターンと組み合わせて使用​​されます。

### ChatStore の実装

ChatStore はツリー構造のメッセージ管理を提供します。

```python
class ChatStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conversations = {}
        return cls._instance
```

各会話は `_conversations[conversation_id]` に保存され、メッセージは `conv["messages"]` リストに保存されます。メッセージは `parent_id` と `children_ids` のツリー構造を形成します。

主な操作: `create_conversation()`、`get_conversation()`、`list_conversations()`、`update_conversation()`、`delete_conversation()`、`add_message()`、`get_message()`、`update_message()`、`delete_message()`、`get_message_chain()`、`branch()`、`search()`、`export_conversation()`。

トリミング操作: `get_messages_range()`、`delete_messages_bulk()`、`insert_message_at()`。

すべてのパブリック メソッドは、`copy.deepcopy()` で戻り値を複製します (参照による意図しない変更を防止します)。

### インスペクターの実装

Inspector は、`collections.deque(maxlen=1000)` + `dict` インデックスを使用してログを管理します。

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

デキューの maxlen を超えると、古いエントリは自動的に削除され、同時に `_index` からも削除されます。

---

## プロバイダー パターン

`BaseProvider` 抽象基本クラスを継承し、各 AI プロバイダの API の違いを吸収するパターン。

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

**StubProvider** — 固定応答を返します。テストと開発用。 API 呼び出しはありません。**OpenAIProvider** — OpenAI API を呼び出します。環境変数 `OPENAI_API_KEY` によって検出されます。**AnthropicProvider** — Anthropic API を呼び出します。環境変数 `ANTHROPIC_API_KEY` によって検出されます。**GoogleProvider** — Google AI API を呼び出します。環境変数 `GOOGLE_API_KEY` によって検出されます。**RumiProvider** — メタプロバイダー。リクエストをパイプライン経由で処理するか、フォールバック プロバイダーに委任します。 AIClient インスタンスを受け取り、1 つ以上の他のプロバイダーが登録されている場合にのみ有効になります。

### プロバイダーの自動検出

`domain/ai_client/providers/__init__.py` の `detect_available_providers()` は、環境変数をチェックし、自動的にインスタンスを生成し、API キーが設定されたプロバイダーを返します。 AIClient の `__init__` 内で呼び出されます。

---

## ビルダーパターン

### ツールビルダー (`domain/tool/builder.py`)

ToolBuilder は、AI を使用してツールのハンドラー コードを生成するヘルパーです。

**generate_skeleton(name, description,parameters)** — JSON スキーマからハンドラー コード スケルトンを生成します。 AI プロバイダーが利用できない場合のフォールバック。

```python
skeleton = generate_skeleton("my_tool", "ツールの説明", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"]
})
```

**generate_handler_code_with_ai(name, description,parameters, model=None)** — AI を使用して完全なハンドラー コードを生成します。モデルが None の場合は、最初に使用可能な非スタブ プロバイダーを使用します。 AI 出力が無効な場合はスケルトンにフォールバックします。

---

## テンプレート パターン

### プロンプト テンプレート (`domain/prompt/template.py`)

パッシブ プロンプト テンプレート式。プロンプトはツール/プロバイダー/権限を移動せず、レンダリングされたテキストをフロー/関数に返します。

**変数展開構文:**

```
{{variable_name}}           — 通常変数（ユーザー指定）
{{context.total_tokens}}    — 特殊変数（実行時に自動注入）
{{context.message_count}}   — 特殊変数
{{context.messages}}        — 特殊変数
{{context.system_prompt}}   — 特殊変数
{{context.conversation_id}} — 特殊変数
```

**主な方法:**

`to_dict()` / `from_dict()` — シリアル化/逆シリアル化。

`to_tool_schema()` — 互換性のある UI の関数ファサードのドラフトを返します。プロンプトツールがオーサリングルートとして登録されていません。

`from_tool_schema()` — ツール定義から PromptTemplate を生成します。

`extract_variable_names()` — 本体の`{{...}}`から変数名を抽出します。

`list_context_variables()` — `context.*` 変数のみを返します。

`list_user_variables()` — `context.*` 以外の変数のみを返します。

### プロンプトマネージャー (`domain/prompt/manager.py`)

PromptManager は、メモリ内の辞書 + `user_data/shared/prompts/` への JSON ファイルの永続化を使用してプロンプトを管理します。 `get_manager()` を使用してモジュールレベルのシングルトンとして取得されます。

**主要なメソッド:** `create_prompt()`、`get_prompt()`、`get_prompt_by_name()`、`list_prompts()`、`update_prompt()`、`delete_prompt()`、`to_template()`、`create_from_template()`、`get_system_prompt()`、`set_system_prompt()`。**コンテキスト変数の挿入:** `inject_context_variables(variables, context)` 静的メソッドは、コンテキスト辞書から `context.total_tokens`、`context.message_count` などの特殊変数を自動的に挿入します。
