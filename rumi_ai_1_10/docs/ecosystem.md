# Rumi AI Ecosystem 開発ガイド

Pack/Component開発者向けの包括的なドキュメントです。

---

## 目次

1. [設計思想](#設計思想)
2. [クイックスタート](#クイックスタート)
3. [Packの構造](#packの構造)
4. [manifest.json仕様](#manifestjson仕様)
5. [setup.py規約](#setuppy規約)
6. [InterfaceRegistry API](#interfaceregistry-api)
7. [EventBus API](#eventbus-api)
8. [Flow定義](#flow定義)
9. [Construct作成](#construct作成)
10. [ライフサイクルフック](#ライフサイクルフック)
11. [ベストプラクティス](#ベストプラクティス)
12. [サンプルコード集](#サンプルコード集)
13. [トラブルシューティング](#トラブルシューティング)

---

## 設計思想

### 贔屓なし（No Favoritism）

Rumi AIの公式コードは、以下の概念を**一切知りません**：

- 「チャット」「メッセージ」
- 「ツール」「プロンプト」
- 「AIクライアント」
- 「フロントエンド」

これらは全て**ecosystemのPack**が定義します。公式が提供するのは：

- InterfaceRegistry（登録箱）
- EventBus（イベント通信）
- Flow実行エンジン（ステップ順次実行）
- Diagnostics（診断情報）

### USBモデル

各Packは互いの存在を知りません。InterfaceRegistryという「共通バス」を通じて疎結合に通信します。

```
┌─────────┐     ┌───────────────────┐     ┌─────────┐
│ Pack A  │────▶│ InterfaceRegistry │◀────│ Pack B  │
└─────────┘     └───────────────────┘     └─────────┘
                        │
                        ▼
                ┌─────────────┐
                │   Kernel    │
                │ (Flow実行)  │
                └─────────────┘
```

### Fail-Soft

エラーが発生してもシステムは停止しません。失敗したコンポーネントは無効化され、診断情報に記録されます。

### AIが生成できるシンプルさ

Pack作成に必要なのは：

1. `manifest.json` - メタデータ
2. `setup.py` - `run(context)` で IR 登録

これだけです。

---

## クイックスタート

### 最小限のPack

```
ecosystem/my_pack/
└── backend/
    ├── ecosystem.json
    └── components/
        └── hello/
            ├── manifest.json
            └── setup.py
```

**ecosystem.json**:
```json
{
  "pack_id": "my_pack",
  "pack_version": "1.0.0",
  "description": "My first pack"
}
```

**manifest.json**:
```json
{
  "type": "service",
  "id": "hello",
  "version": "1.0.0",
  "connectivity": {
    "provides": ["service.hello"],
    "requires": []
  }
}
```

**setup.py**:
```python
def run(context):
    ir = context["interface_registry"]
    
    def hello_handler(args, ctx):
        name = args.get("name", "World")
        return {"message": f"Hello, {name}!"}
    
    ir.register("service.hello", hello_handler)
```

これで `ir.get("service.hello")` から `hello_handler` を取得できます。

---

## Packの構造

### ディレクトリ構造

```
ecosystem/{pack_id}/
├── backend/
│   ├── ecosystem.json          # Pack全体のメタデータ
│   └── components/
│       └── {component_id}/
│           ├── manifest.json   # Componentメタデータ
│           ├── setup.py        # 初期化（必須）
│           └── (その他のファイル)
└── frontend/                   # オプション（UIコンポーネント用）
```

### Pack種別

| 種別 | `pack_type` | 用途 | ロード順序 |
|------|------------|------|-----------|
| 通常 | `"pack"` | 一般的な機能提供 | requires解決後 |
| ライブラリ | `"library"` | ヘルパー関数提供 | 優先（他packより先） |

---

## manifest.json仕様

### 必須フィールド

```json
{
  "type": "service",
  "id": "my_component",
  "version": "1.0.0"
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `type` | string | コンポーネントの種類（自由に定義可） |
| `id` | string | Pack内で一意のID |
| `version` | string | セマンティックバージョン |

### オプションフィールド

```json
{
  "type": "ai_client",
  "id": "openai",
  "version": "1.0.0",
  "connectivity": {
    "provides": ["ai.client", "ai.client.openai"],
    "requires": ["config.api_key"]
  },
  "description": "OpenAI API client",
  "author": "Your Name"
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `connectivity.provides` | string[] | このコンポーネントが提供するキー |
| `connectivity.requires` | string[] | 依存するキー（起動順序に影響） |
| `description` | string | 説明文 |
| `author` | string | 作者名 |

### type の例

公式は `type` の値を制限しません。一般的な例：

- `service` - バックエンドサービス
- `ai_client` - AIプロバイダー接続
- `tool` - ツール定義
- `prompt` - プロンプトテンプレート
- `frontend` - UIコンポーネント
- `library` - ヘルパーライブラリ

---

## setup.py規約

### 基本形

```python
def run(context):
    """
    コンポーネント初期化
    
    Args:
        context: {
            "interface_registry": InterfaceRegistry,
            "event_bus": EventBus,
            "diagnostics": Diagnostics,
            "install_journal": InstallJournal,
            "phase": str,
            "ids": {
                "component_full_id": str,
                "component_type": str,
                "component_id": str,
                "pack_id": str
            },
            "paths": {
                "component_runtime_dir": str,
                "mounts": dict
            }
        }
    """
    ir = context["interface_registry"]
    eb = context["event_bus"]
    
    # ここで初期化処理を行う
    pass
```

### 呼び出し規約

Kernelは以下の順序で関数を探します：

1. `run(context)` - 推奨
2. `main(context)` - 代替
3. なし - import副作用のみ

### context の内容

| キー | 型 | 説明 |
|-----|---|------|
| `interface_registry` | InterfaceRegistry | サービス登録箱 |
| `event_bus` | EventBus | イベント通信 |
| `diagnostics` | Diagnostics | 診断情報 |
| `install_journal` | InstallJournal | インストール履歴 |
| `phase` | str | 現在のフェーズ名 |
| `ids.component_full_id` | str | `{pack_id}:{type}:{id}` |
| `ids.pack_id` | str | Pack ID |
| `paths.component_runtime_dir` | str | コンポーネントのディレクトリ |
| `paths.mounts` | dict | マウントポイント辞書 |

---

## InterfaceRegistry API

### 基本操作

#### register(key, value, meta=None)

値を登録します。同じキーへの複数登録が可能です（後勝ち）。

```python
# 基本的な登録
ir.register("my.service", my_function)

# メタデータ付き
ir.register("my.service", my_function, meta={
    "version": "1.0.0",
    "description": "My service"
})

# source_component を含めると、Hot Reload時に追跡可能
ir.register("my.service", my_function, meta={
    "_source_component": context.get("_source_component")
})
```

#### get(key, strategy="last")

値を取得します。

```python
# 最新の値を取得（デフォルト）
service = ir.get("my.service")

# 最初に登録された値を取得
service = ir.get("my.service", strategy="first")

# 全ての値をリストで取得
all_services = ir.get("my.service", strategy="all")  # []（空でも配列）
```

| strategy | 戻り値 |
|----------|--------|
| `"last"` | 最新の値、なければ `None` |
| `"first"` | 最初の値、なければ `None` |
| `"all"` | 全ての値のリスト、なければ `[]` |

#### register_if_absent(key, value, meta=None, ttl=None)

キーが存在しない場合のみ登録（アトミック）。分散ロックに使用可能。

```python
# 最初に登録したものが勝つ
if ir.register_if_absent("lock.resource", {"owner": "me"}):
    # ロック取得成功
    try:
        # 処理
        pass
    finally:
        ir.unregister("lock.resource")
else:
    # 既にロックされている
    pass
```

### Handler登録

#### register_handler(key, handler, input_schema=None, output_schema=None, meta=None, source_code=None)

スキーマ情報付きでhandlerを登録。OpenAPI自動生成等に使用。

```python
ir.register_handler(
    "api.users.create",
    create_user_handler,
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string", "format": "email"}
        },
        "required": ["name", "email"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"}
        }
    }
)
```

#### get_schema(key)

登録されたスキーマを取得。

```python
input_schema, output_schema = ir.get_schema("api.users.create")
```

#### get_source(key)

登録時に指定されたソースコードを取得。

```python
source = ir.get_source("api.users.create")
```

### Observer（変更監視）

#### observe(key_or_pattern, callback, immediate=False)

キーまたはパターンの変更を監視。

```python
def on_state_change(key, old_value, new_value):
    print(f"{key}: {old_value} -> {new_value}")

# 特定のキーを監視
observer_id = ir.observe("state.counter", on_state_change)

# パターンで監視（ワイルドカード対応）
observer_id = ir.observe("state.*", on_state_change)

# 即座に現在値を通知
observer_id = ir.observe("state.counter", on_state_change, immediate=True)
```

#### unobserve(observer_id)

監視を解除。

```python
ir.unobserve(observer_id)
```

#### unobserve_all(pattern=None)

パターンに一致する全てのobserverを解除。

```python
ir.unobserve_all("state.*")  # state.*の監視を全て解除
ir.unobserve_all()           # 全ての監視を解除
```

### 一時的な上書き

#### temporary_override(key, value, meta=None)

テスト等で一時的に値を上書き。withブロック終了時に自動復元。

```python
# 本番のhandler
ir.register("ai.client", production_ai_client)

# テスト時にモックに差し替え
with ir.temporary_override("ai.client", mock_ai_client):
    # ここではmock_ai_clientが使われる
    result = ir.get("ai.client")(args, ctx)

# ここではproduction_ai_clientに戻っている
```

### 検索・一覧

#### list(prefix=None, include_meta=False)

登録状況を一覧。

```python
# 全てのキーと登録数
all_keys = ir.list()  # {"my.service": 2, "other.service": 1}

# プレフィックスでフィルタ
ai_keys = ir.list(prefix="ai.")  # {"ai.client": 1, "ai.model": 1}

# メタデータ付き
detailed = ir.list(include_meta=True)
# {"my.service": {"count": 2, "last_ts": "...", "last_meta": {...}}}
```

#### find(predicate)

条件に一致するエントリを検索。

```python
# バージョン1.0.0のエントリを検索
entries = ir.find(lambda key, entry: 
    entry.get("meta", {}).get("version") == "1.0.0"
)
```

#### unregister(key, predicate=None)

登録解除。

```python
# キー配下を全削除
count = ir.unregister("my.service")

# 条件一致のみ削除
count = ir.unregister("my.service", lambda entry: 
    entry.get("meta", {}).get("deprecated") == True
)
```

---

## EventBus API

### 基本操作

#### subscribe(topic, handler, handler_id=None)

トピックを購読。

```python
def on_user_created(payload):
    print(f"User created: {payload['user_id']}")

# 購読（IDは自動生成）
handler_id = eb.subscribe("user.created", on_user_created)

# ID指定
handler_id = eb.subscribe("user.created", on_user_created, handler_id="my_handler")
```

#### publish(topic, payload)

イベントを発行。

```python
eb.publish("user.created", {"user_id": "123", "name": "Alice"})
```

#### unsubscribe(topic, handler_id)

購読解除。

```python
eb.unsubscribe("user.created", handler_id)
```

#### clear(topic=None)

購読を一括解除。

```python
eb.clear("user.created")  # 特定トピック
eb.clear()                 # 全て
```

#### list_subscribers()

購読状況を取得。

```python
subs = eb.list_subscribers()
# {"user.created": ["h1", "h2"], "order.placed": ["h3"]}
```

---

## Flow定義

### 基本概念

FlowはInterfaceRegistryに登録されたステップの定義です。Kernelはこれを取得して順次実行します。

```python
# Flowを登録
ir.register("flow.my_flow", {
    "steps": [
        {"handler": "step1.handler", "id": "step1"},
        {"handler": "step2.handler", "id": "step2"}
    ]
})

# Flowを実行
result = kernel.execute_flow_sync("my_flow", {"input": "data"})
```

### ステップ定義

#### 基本形

```python
{
    "id": "unique_step_id",      # オプション、デフォルトは step_0, step_1...
    "handler": "my.handler",     # IRから取得するキー
    "args": {                     # handlerに渡す引数
        "param1": "value1",
        "param2": "${ctx.input}"  # 変数展開
    },
    "output": "result",          # 結果をctxに格納するキー
    "when": "${ctx.enabled} == True"  # 条件（省略可）
}
```

#### 変数展開

`${ctx.xxx}` 形式でコンテキストの値を参照できます。

```python
{
    "handler": "api.call",
    "args": {
        "user_id": "${ctx.user.id}",      # ネストしたパス
        "settings": "${ctx.config}"        # オブジェクト全体
    }
}
```

#### 条件付き実行

`when` で条件を指定できます。

```python
{
    "handler": "premium.feature",
    "when": "${ctx.user_type} == premium"  # == と != をサポート
}
```

### handler の実装

```python
def my_handler(args, ctx):
    """
    Args:
        args: Flowで定義されたargs（変数展開済み）
        ctx: 実行コンテキスト（読み書き可能）
    
    Returns:
        任意の値（outputが指定されていればctxに格納）
    """
    input_data = args.get("input")
    
    # ctxを直接変更することも可能
    ctx["processed"] = True
    
    return {"result": "success"}
```

### async handler

async関数も使用可能です。

```python
async def async_handler(args, ctx):
    result = await external_api_call(args)
    return result

ir.register("api.async_call", async_handler)
```

### Flow実行API

#### execute_flow（async）

```python
result = await kernel.execute_flow("my_flow", context={"input": "data"}, timeout=30.0)
```

#### execute_flow_sync（sync）

```python
result = kernel.execute_flow_sync("my_flow", context={"input": "data"}, timeout=30.0)
```

### Flow永続化

```python
# ファイルに保存
path = kernel.save_flow_to_file("my_flow", flow_def, "user_data/flows")

# ファイルから読み込み（startupで自動実行）
loaded = kernel.load_user_flows("user_data/flows")
```

---

## Construct作成

Constructは `loop`, `branch`, `parallel` などの制御構造です。

### 組み込みConstruct

#### loop

```python
{
    "type": "loop",
    "exit_when": "${ctx.done} == True",
    "max_iterations": 100,
    "steps": [
        {"handler": "process.item"}
    ]
}
```

| パラメータ | 型 | 説明 |
|-----------|---|------|
| `exit_when` | string | 終了条件 |
| `max_iterations` | int | 最大反復回数（デフォルト: 100） |
| `steps` | array | 内部ステップ |

#### branch

```python
{
    "type": "branch",
    "condition": "${ctx.user_type} == premium",
    "then": [
        {"handler": "premium.features"}
    ],
    "else": [
        {"handler": "basic.features"}
    ]
}
```

| パラメータ | 型 | 説明 |
|-----------|---|------|
| `condition` | string | 分岐条件 |
| `then` | array | 条件が真のときのステップ |
| `else` | array | 条件が偽のときのステップ |

#### parallel

```python
{
    "type": "parallel",
    "branches": [
        {"name": "api1", "steps": [{"handler": "api.call1"}]},
        {"name": "api2", "steps": [{"handler": "api.call2"}]}
    ]
}
```

結果は `ctx["_parallel_results"]` に格納されます。

**⚠️注意**: 各branchがIR/EventBusに書き込む場合は競合に注意。読み取り専用処理向け。

#### group

条件付きでステップグループをスキップ。

```python
{
    "type": "group",
    "when": "${ctx.feature_enabled} == True",
    "steps": [
        {"handler": "feature.step1"},
        {"handler": "feature.step2"}
    ]
}
```

#### retry

```python
{
    "type": "retry",
    "handler": "unreliable.api",
    "max_attempts": 3,
    "delay_ms": 1000,
    "args": {"param": "value"},
    "output": "result"
}
```

| パラメータ | 型 | 説明 |
|-----------|---|------|
| `max_attempts` | int | 最大試行回数（デフォルト: 3） |
| `delay_ms` | int | リトライ間隔（ミリ秒） |

### カスタムConstruct作成

```python
def run(context):
    ir = context["interface_registry"]
    
    def my_construct(kernel, step, ctx):
        """
        カスタムConstruct
        
        Args:
            kernel: Kernelインスタンス
            step: Flowステップ定義
            ctx: 実行コンテキスト
        
        Returns:
            更新されたctx
        """
        # ステップのパラメータを取得
        inner_steps = step.get("steps", [])
        custom_param = step.get("custom_param")
        
        # 内部ステップを実行
        import asyncio
        try:
            asyncio.get_running_loop()
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor() as pool:
                ctx = pool.submit(
                    asyncio.run, 
                    kernel._execute_steps_async(inner_steps, ctx)
                ).result()
        except RuntimeError:
            ctx = asyncio.run(kernel._execute_steps_async(inner_steps, ctx))
        
        return ctx
    
    ir.register("flow.construct.my_construct", my_construct)
```

使用：

```python
{
    "type": "my_construct",
    "custom_param": "value",
    "steps": [...]
}
```

---

## ライフサイクルフック

### before_step

各ステップ実行前に呼ばれます。

```python
def before_step_hook(step, ctx, meta):
    """
    Args:
        step: ステップ定義
        ctx: コンテキスト
        meta: {
            "flow_id": str,
            "execution_id": str,
            "step_index": int,
            "total_steps": int,
            "parent_execution_id": str or None
        }
    
    Returns:
        None または {"_skip": True} または {"_abort": True}
    """
    print(f"Executing: {step.get('id')} ({meta['step_index']}/{meta['total_steps']})")
    
    # ステップをスキップ
    if should_skip(step):
        return {"_skip": True}
    
    # Flow全体を中止
    if should_abort(ctx):
        return {"_abort": True}

ir.register("flow.hooks.before_step", before_step_hook)
```

### after_step

各ステップ実行後に呼ばれます。

```python
def after_step_hook(step, ctx, result, meta):
    """
    Args:
        step: ステップ定義
        ctx: コンテキスト
        result: ステップの戻り値
        meta: メタデータ
    """
    print(f"Completed: {step.get('id')}, result: {result}")

ir.register("flow.hooks.after_step", after_step_hook)
```

### error_handler

ステップでエラー発生時に呼ばれます。

```python
def error_handler(step, ctx, error):
    """
    Args:
        step: ステップ定義
        ctx: コンテキスト
        error: 発生した例外
    
    Returns:
        "abort" - Flow全体を中止
        "retry" - 同じステップを再実行
        "continue" - 次のステップへ（デフォルト動作）
    """
    if isinstance(error, NetworkError):
        return "retry"
    if isinstance(error, FatalError):
        return "abort"
    return "continue"

ir.register("flow.error_handler", error_handler)
```

---

## ベストプラクティス

### 1. キー命名規約

```python
# 良い例
ir.register("service.users.create", handler)
ir.register("ai.client.openai", client)
ir.register("tool.calculator", tool)

# 悪い例
ir.register("myHandler", handler)  # ドット区切りを使う
ir.register("SERVICE_USERS", handler)  # 小文字を使う
```

### 2. source_component の記録

Hot Reload対応のため、metaに記録します。

```python
ir.register("my.service", handler, meta={
    "_source_component": context.get("_source_component")
})
```

### 3. fail-soft の維持

エラーをキャッチして診断情報に記録します。

```python
def run(context):
    ir = context["interface_registry"]
    diagnostics = context["diagnostics"]
    
    try:
        # 初期化処理
        pass
    except Exception as e:
        diagnostics.record_step(
            phase="setup",
            step_id="my_component.init",
            handler="my_component:setup",
            status="failed",
            error=e
        )
        # 例外を再raiseしない（fail-soft）
```

### 4. 依存関係の明示

manifest.jsonで依存を宣言します。

```json
{
  "connectivity": {
    "provides": ["my.service"],
    "requires": ["config.database"]  # これが先にロードされる
  }
}
```

### 5. 設定の外部化

ハードコードを避け、IRから設定を取得します。

```python
def run(context):
    ir = context["interface_registry"]
    
    # 設定を取得（なければデフォルト）
    config = ir.get("config.my_service") or {
        "timeout": 30,
        "retry_count": 3
    }
    
    def handler(args, ctx):
        # configを使用
        pass
```

---

## サンプルコード集

### 1. AIクライアント

```python
# ecosystem/my_ai/backend/components/openai_client/setup.py
import os

def run(context):
    ir = context["interface_registry"]
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return  # APIキーがなければ登録しない
    
    async def generate(args, ctx):
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": args.get("model", "gpt-4"),
                    "messages": args.get("messages", [])
                },
                timeout=60.0
            )
            return response.json()
    
    ir.register_handler(
        "ai.generate",
        generate,
        input_schema={
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "messages": {"type": "array"}
            }
        },
        meta={"_source_component": context.get("_source_component")}
    )
```

### 2. ツール定義

```python
# ecosystem/tools/backend/components/calculator/setup.py
def run(context):
    ir = context["interface_registry"]
    
    def calculator(args, ctx):
        expression = args.get("expression", "")
        try:
            # 安全な評価（実際はより厳密に）
            allowed = set("0123456789+-*/.(). ")
            if all(c in allowed for c in expression):
                result = eval(expression)
                return {"result": result}
            return {"error": "Invalid expression"}
        except Exception as e:
            return {"error": str(e)}
    
    ir.register("tool.calculator", calculator, meta={
        "description": "数式を計算します",
        "parameters": {
            "expression": "計算する数式（例: 2+3*4）"
        }
    })
```

### 3. HTTP APIエンドポイント

```python
# ecosystem/api/backend/components/user_api/setup.py
def run(context):
    ir = context["interface_registry"]
    
    def api_binder(app, kernel, ctx):
        from flask import request, jsonify
        
        @app.route("/api/users", methods=["GET"])
        def list_users():
            users = ir.get("service.users.list")
            if users:
                return jsonify(users({}, {}))
            return jsonify({"error": "Service not available"}), 503
        
        @app.route("/api/users", methods=["POST"])
        def create_user():
            handler = ir.get("service.users.create")
            if handler:
                result = handler(request.json, {})
                return jsonify(result)
            return jsonify({"error": "Service not available"}), 503
    
    ir.register("io.http.binders", api_binder)
```

### 4. メッセージ処理Flow

```python
# ecosystem/chat/backend/components/chat_flow/setup.py
def run(context):
    ir = context["interface_registry"]
    
    # メッセージ処理Flow
    ir.register("flow.message", {
        "steps": [
            {
                "id": "validate",
                "handler": "message.validate",
                "args": {"input": "${ctx.payload}"},
                "output": "validated"
            },
            {
                "id": "process",
                "handler": "message.process",
                "args": {"message": "${ctx.validated}"},
                "output": "processed"
            },
            {
                "id": "ai_generate",
                "handler": "ai.generate",
                "args": {
                    "messages": "${ctx.processed.messages}"
                },
                "output": "ai_response"
            },
            {
                "id": "format",
                "handler": "message.format",
                "args": {"response": "${ctx.ai_response}"},
                "output": "output"
            }
        ]
    })
```

### 5. WebSocket双方向通信

```python
# ecosystem/realtime/backend/components/websocket/setup.py
def run(context):
    ir = context["interface_registry"]
    
    def websocket_binder(app, kernel, ctx):
        try:
            from flask_sock import Sock
            sock = Sock(app)
            
            @sock.route("/ws")
            def ws_handler(ws):
                while True:
                    message = ws.receive()
                    if message:
                        result = kernel.execute_flow_sync("message", {
                            "payload": {"content": message}
                        })
                        ws.send(str(result.get("output", "")))
            
            # 状態変更をクライアントに通知
            def on_state_change(key, old_val, new_val):
                # WebSocketで全クライアントにブロードキャスト
                pass
            
            ir.observe("state.*", on_state_change)
            
        except ImportError:
            pass  # flask-sock がなければスキップ
    
    ir.register("io.http.binders", websocket_binder)
```

---

## トラブルシューティング

### handlerが見つからない

```python
# 確認方法
print(ir.list(prefix="my."))

# よくある原因
# 1. setup.pyでregisterしていない
# 2. manifest.jsonのprovidesと実際のキーが不一致
# 3. 依存するpackがロードされていない
```

### Flowがタイムアウト

```python
# タイムアウトを延長
result = kernel.execute_flow_sync("my_flow", ctx, timeout=120.0)

# タイムアウトなし（非推奨）
result = kernel.execute_flow_sync("my_flow", ctx, timeout=None)
```

### 循環依存エラー

```
_error: "Recursive flow: flow_a -> flow_b -> flow_a"
```

Flow A が Flow B を呼び、Flow B が Flow A を呼んでいます。設計を見直してください。

### IR.getがNoneを返す

```python
# strategy="all" を使うと空でも [] が返る
handlers = ir.get("my.handlers", strategy="all")
for h in handlers:  # 空でもエラーにならない
    h(args, ctx)
```

### async handlerでエラー

```python
# 正しい実装
async def my_handler(args, ctx):
    result = await some_async_operation()
    return result

# 間違い（asyncなのにawaitしていない）
async def my_handler(args, ctx):
    result = some_async_operation()  # awaitがない
    return result
```

---

## 付録: 完全なPack例

```
ecosystem/example_pack/
├── backend/
│   ├── ecosystem.json
│   └── components/
│       ├── service/
│       │   ├── manifest.json
│       │   └── setup.py
│       └── flow/
│           ├── manifest.json
│           └── setup.py
└── README.md
```

### ecosystem.json

```json
{
  "pack_id": "example_pack",
  "pack_version": "1.0.0",
  "description": "Example pack demonstrating all features",
  "author": "Your Name",
  "components": {
    "service": {
      "type": "service",
      "id": "example_service",
      "version": "1.0.0"
    },
    "flow": {
      "type": "flow",
      "id": "example_flow",
      "version": "1.0.0"
    }
  }
}
```

### components/service/manifest.json

```json
{
  "type": "service",
  "id": "example_service",
  "version": "1.0.0",
  "connectivity": {
    "provides": ["service.example", "service.example.process"],
    "requires": []
  }
}
```

### components/service/setup.py

```python
"""Example Service Component"""

def run(context):
    ir = context["interface_registry"]
    eb = context["event_bus"]
    src = context.get("_source_component", "example_pack:service:example_service")
    
    def process_handler(args, ctx):
        data = args.get("data")
        result = {"processed": data, "status": "ok"}
        eb.publish("service.example.processed", result)
        return result
    
    ir.register_handler(
        "service.example.process",
        process_handler,
        input_schema={"type": "object", "properties": {"data": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"processed": {"type": "string"}}},
        meta={"_source_component": src}
    )
    
    # サービス全体を登録
    ir.register("service.example", {
        "process": ir.get("service.example.process")
    }, meta={"_source_component": src})
```

### components/flow/manifest.json

```json
{
  "type": "flow",
  "id": "example_flow",
  "version": "1.0.0",
  "connectivity": {
    "provides": ["flow.example"],
    "requires": ["service.example.process"]
  }
}
```

### components/flow/setup.py

```python
"""Example Flow Component"""

def run(context):
    ir = context["interface_registry"]
    src = context.get("_source_component", "example_pack:flow:example_flow")
    
    ir.register("flow.example", {
        "steps": [
            {
                "id": "validate",
                "handler": "service.example.process",
                "args": {"data": "${ctx.input}"},
                "output": "validated"
            },
            {
                "type": "branch",
                "condition": "${ctx.validated.status} == ok",
                "then": [
                    {"handler": "service.example.process", "args": {"data": "success"}}
                ],
                "else": [
                    {"handler": "service.example.process", "args": {"data": "failed"}}
                ]
            }
        ]
    }, meta={"_source_component": src})
```

---
