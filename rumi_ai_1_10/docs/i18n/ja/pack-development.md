<!-- docs-i18n-links:start -->
[EN](../../pack-development.md) | [JP](./pack-development.md) | [KR](../ko/pack-development.md) | [CN](../zh-cn/pack-development.md)
<!-- docs-i18n-links:end -->

> **クイック スタート ガイド**: パック開発を開始する場合は、[パック開発クイック スタート ガイド](./pack-development-guide.md)を参照してください。
# Rumi AI OS — パック開発ガイド

Pack 開発者向けのガイド。全体的な設計については [architecture.md](./architecture.md) を、操作手順については [operations.md](./operations.md) を参照してください。

---

## 目次

1. 【開発フロー】(#開発の流れ)
2. [最小構成](#minimum-configuration)
3. [ecosystem.json](#エコシステムjson)
4. [ブロック](#ブロック)
5. [Type hints/validation](#型のヒント検証)
6. [フロー定義](#フローの定義)
7. [フロー → HTTP レスポンス マッピング](#flow--http-response-mapping)
8. [フローモディファイア](#フローモディファイアー)
9. [ネットワークアクセス](#ネットワークアクセス)
10. [context\["http\_request"\] 詳細仕様](#contexthttp_request-詳細仕様)
11. [シークレットの使用(パックから)](#シークレットの使用-パックから)
12. [能力の使用](#機能の使用)
13. [ストア API (機能経由)](#ストア-api-機能経由)
14. [パック間連携パターン](#パック間連携パターン)
15. [lib（install / update）](#libinstall--update)
16. [pip 依存関係 (requirements.lock)](#pip-依存関係-requirementslock)
17. [permissions.json](#権限json)
18. [ケイパビリティハンドラを含む](#includes-capability-handler)
19. [vocab/converter (advanced)](#語彙コンバーター-上級)
20. [コンポーネント(上級)](#コンポーネント-上級)
21. [パック固有のエンドポイント (routes.json)](#パック固有のエンドポイント-routesjson)
22. [HTTPステータスコード制御](#httpステータスコード制御)
23. [エラー処理のベストプラクティス](#エラー処理のベストプラクティス)
24. [フローモディファイア推奨パターン](#flow-modifier-推奨パターン)
25. [ハンドラAPI分類](#ハンドラー-api-の分類)
26. [出力キーの命名規則(詳細)](#出力キーの命名規則-詳細)
27. [メモ](#注意事項)
28. [APIリファレンス](#apiリファレンス)
29. [チュートリアル: 簡単なパックの作成](#チュートリアル-簡単なパックを作成する)

---

## 開発の流れ

### ステップ 0: テンプレートを使用してテンプレートを生成する

```bash
python -m core_runtime.pack_scaffold my-pack --template minimal --output-dir ecosystem/
```

テンプレートの種類:
- `minimal`: 最小構成 (ecosystem.json + run.py)
- `capability`: ケイパビリティハンドラーあり
- `flow`: フロー定義あり
- `full`：すべて含まれています

1. **パックの作成** — `ecosystem/<pack_id>/backend/` にファイルを配置します。
2. **ecosystem.json の書き込み** — メタデータのパック (`pack_id`、`pack_identity` が必要)
3. **ブロックの書き込み/** — `python_file_call` で呼び出されるコード
4. **書き込みフロー** — Pack and connect ブロックの `user_data/shared/flows/` または `flows/` に配置します。
5. **承認の取得** — ユーザーがパックを承認します
6. **実行** — 承認後、フローの実行時にブロックが呼び出されます

---

## 最小限の構成

```
ecosystem/my_pack/
└── backend/
    ├── ecosystem.json
    └── blocks/
        └── hello.py
```

> **パスについて**: `ecosystem/<pack_id>/` が推奨パスです。 `ecosystem/packs/<pack_id>/`も互換パスとしてサポートされていますが、両方に同じ`pack_id`が存在する場合、`ecosystem/<pack_id>/`が優先されます。

---

## エコシステム.json

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "version": "1.0.0",
  "description": "My first pack",
  "pack_identity_vocabulary": ["my_pack"]
}
```

|フィールド |必須 |説明 |
|-----------|------|------|
| `pack_id` | ✅ |パックの識別子。ディレクトリ名を一致させる |
| `pack_identity` | ✅ |ディストリビュータ識別子 (例: `github:author/repo`)。パックの更新中にこの値が変更された場合、適用は拒否されます。
| `version` |オプション |セマンティック バージョニング |
| `description` |オプション |説明 |
| `pack_identity_vocabulary` |オプション | Pack で使用される語彙のリスト。 vocab.txt とのコラボレーションに使用 |
| `required_secrets` |オプション |必要な秘密鍵のリスト (例: `["OPENAI_API_KEY"]`)。ユーザーへの情報提供のため｜
| `required_network` |オプション |ネットワーク要件 (例: `{"allowed_domains": ["api.example.com"], "allowed_ports": [443]}`)。ユーザーへの情報提供のため｜
| `host_execution` |オプション |ホスト実行の必要性 (`true` / `false`)。 `true` の場合、コンテナ分離ではなくホスト プロセスとして実行します。

### 接続性 (パック間の依存関係の宣言)

`connectivity` フィールドを `ecosystem.json` に追加することで、パック間の依存関係を宣言できます。

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "connectivity": {
    "provides": ["ai.client"],
    "requires": ["tool.registry"]
  }
}
```

|フィールド |説明 |
|-----------|------|
| `provides` |このパックで提供されるサービス名一覧 |
| `requires` |このパックに必要なサービス名のリスト |

接続 `requires` / `provides` は、起動時にパックのロード順序 (load_order) を自動的に解決するために使用されます。 `provides` `requires` で指定されたサービスを含むパックが最初にロードされます。

手動指定 (`ecosystem.json` の `load_order` フィールド) が存在する場合、それが優先されます。自動解決は、手動指定がない場合にのみ適用されます。

現在、接続による実行時の影響は、load_order の自動解決のみです。将来的には拡張される可能性があります。

#### 接続パターンの例

| |を提供します意味 |典型的なパック |
|----------|------|--------------|
| `ai.client` | AI API クライアント | OpenAI / Anthropic クライアント |
| `tool.registry` |ツール登録 |ツールマネージャー |
| `memory.store` |メモリストア |メモリ管理 |
| `ui.chat` |チャットUI |フロントエンド |

Provides / Required の値はドットで区切られた自由な文字列です。 OS は値の意味を解釈せず、load_order の自動解決にのみ使用します。パック開発者間で名前を一致させてください。

---

## ブロック

`python_file_call` によって呼び出される Python ファイル。

### 基本形

```python
# ecosystem/my_pack/backend/blocks/hello.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ（dict）
        context: 実行コンテキスト（dict）
            - flow_id: 実行中の Flow ID
            - step_id: 実行中のステップ ID
            - phase: 実行中のフェーズ名
            - ts: タイムスタンプ
            - owner_pack: 所有 Pack ID
            - inputs: 入力データ
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> dict
            - capability_socket: Capability UDS ソケットパス（存在する場合）

    Returns:
        JSON 互換の dict
    """
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

`run` 関数では、引数が 1 つのバージョンの `input_data` のみを使用できます。

### 戻り値

JSON 互換の辞書を返してください。返された値は、フローの `output` フィールドで指定されたコンテキスト キーにそのまま格納されます。カーネル内のラッパー (`_kernel_step_status` など) は自動的に削除され、ブロックによって返された値は直接 `ctx[output_key]` に入ります。

### 出力キーの命名規則

フローステップの`output`に格納される値のキー名には、次の規則が適用されます。

`_` プレフィックスで始まるキーは、カーネル内部キーとして予約されています。 `python_file_call` の `run()` によって返された辞書に `_` 接頭辞を持つキー (例: `_kernel_step_status`、`_debug`) が含まれている場合、それらはフローの `output` コンテキストに格納されるときに自動的に除外されます。

Pack ブロックによって返される出力キーには `_` プレフィックスを使用しないでください。これにより、意図せずに除外される可能性があります。

```python
# NG: _ プレフィックスは除外される
def run(input_data, context=None):
    return {"_internal": "removed", "result": "kept"}
    # ctx に格納されるのは {"result": "kept"} のみ

# OK: プレフィックスなし
def run(input_data, context=None):
    return {"result": "kept", "metadata": {"source": "my_pack"}}
```

---

## タイプのヒント/検証

### run() 関数のシグネチャ

`python_file_call` によって呼び出される `run()` 関数は、次の 3 つのパターンのいずれかを受け入れます。実行エンジンは、`inspect.signature` の引数の数を自動検出します。

```python
# パターン1: 入力データとコンテキストの両方を受け取る（推奨）
def run(input_data: dict, context: dict) -> dict | None:
    ...

# パターン2: 入力データのみ受け取る
def run(input_data: dict) -> dict | None:
    ...

# パターン3: 引数なし
def run() -> dict | None:
    ...
```

### input_data のタイプ セーフティ

`input_data` は、フロー定義の `input` フィールドの JSON シリアル化/逆シリアル化された値です。したがって、含まれる型は次の JSON 派生型に限定されます。

| JSON タイプ | Python の種類 |
|---------|----------|
|オブジェクト | `dict` |
|配列 | `list` |
|文字列 | `str` |
|数値 (整数) | `int` |
|数値 (10 進数) | `float` |
|ブール値 | `bool` |
|ヌル | `None` |

`input_data`自体は通常は`dict`ですが、フロー定義に直接スカラー値やリストを指定した場合はその型になります。

### コンテキストタイプ

`context`は`dict[str, Any]`です。主なキーは次のとおりです。

|キー |タイプ |説明 |
|------|----|------|
| `flow_id` | `str` |実行中のフロー ID |
| `step_id` | `str` |実行中のステップ ID |
| `phase` | `str` |実行フェーズ名 |
| `ts` | `str` |実行開始タイムスタンプ (ISO 8601 UTC) |
| `owner_pack` | `str \| None` |所有パック ID |
| `inputs` | `dict` | input_data と同じ |
| `http_request` | `Callable` | HTTP リクエスト関数 ([context\["http\_request"\] 詳細仕様](#contexthttp_request-詳細仕様) を参照)
| `network_check` | `Callable` |ネットワークアクセスチェック機能 |
| `capability_socket` | `str \| None` |機能 UDS ソケット パス |

### 戻り値の型

`run()` の戻り値は、JSON シリアル化可能な値 (`dict`、`list`、`str`、`int`、`float`、`bool`、`None`) である必要があります。 `None` を返すと、フロー出力は `null` として扱われます。戻り値が`dict`の場合、その内容はフローの`output`変数に格納されます。

### 検証のベストプラクティス

`input_data` の内容は外部ソース (フロー定義とユーザー入力) から派生しているため、必ず検証してください。

```python
def run(input_data: dict, context: dict) -> dict:
    # 1. 型チェック（早期リターン）
    if not isinstance(input_data, dict):
        return {"error": "input_data must be a dict"}

    # 2. 必須フィールドの存在チェック
    url = input_data.get("url")
    if not url:
        return {"error": "missing required field: url"}

    # 3. 型の厳密チェック
    if not isinstance(url, str):
        return {"error": "field 'url' must be a string"}

    timeout = input_data.get("timeout", 30)
    if not isinstance(timeout, (int, float)):
        return {"error": "field 'timeout' must be a number"}

    # 4. 値の範囲チェック
    if timeout <= 0 or timeout > 120:
        return {"error": "field 'timeout' must be between 0 and 120"}

    # 5. 本処理
    result = context["http_request"](
        method="GET",
        url=url,
        timeout_seconds=timeout,
    )
    return {"result": result}
```

**推奨事項:**

- 例外をスローする代わりに、`{"error": "..."}` を返し、通常どおり終了します。
- 関数の先頭ですべての必須フィールドをチェックしてください
- `isinstance()` で型を厳密にチェックする
- 数値範囲とリストの長さに制限を設定する

---

## フロー定義

### 配置パス

|パス |目的 |
|------|------|
| `user_data/shared/flows/` |共有フロー。複数のパック間の配線に最適 |
| `ecosystem/<pack_id>/backend/flows/` |パック固有のフロー |

### 例

```yaml
# user_data/shared/flows/hello.flow.yaml

flow_id: hello
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "${ctx.name}"
    output: greeting
```

### ステップの書き方

#### python_file_call

```yaml
- id: generate_response
  phase: generate
  priority: 50
  type: python_file_call
  owner_pack: ai_client
  file: blocks/generate.py
  input:
    user_input: "${ctx.user_input}"
  output: ai_output
  timeout_seconds: 60
```

|フィールド |必須 |説明 |
|-----------|------|------|
| `id` | ✅ |ステップ ID (フロー内で一意) |
| `phase` | ✅ |所属段階 |
| `priority` |オプション |実行優先度 (昇順、デフォルトは 100) |
| `type` | ✅ | `python_file_call` |
| `owner_pack` |オプション |所有パック (パスから推測される場合は省略可能) |
| `file` | ✅ |実行可能ファイルの相対パス |
| `input` |任意 |入力データ（変数拡張可能） |
| `output` |オプション |出力先コンテキストキー |
| `timeout_seconds` |オプション |タイムアウト秒 (デフォルトは 60) |

#### ハンドラー

```yaml
- id: load_context
  phase: prepare
  priority: 10
  type: handler
  input:
    handler: "kernel:ctx.get"
    args:
      key: "context"
  output: context
```

`handler` 型は、`input.handler` (`kernel:*`) で指定されたカーネル ハンドラ、または InterfaceRegistry に登録されたハンドラを直接呼び出します。 `input.args` は引数としてハンドラーに渡されます。

#### セット

```yaml
- id: set_default
  phase: prepare
  priority: 5
  type: set
  input:
    key: "model"
    value: "gpt-4"
```

> **注意**: `set` タイプは、InterfaceRegistry に登録されている `flow.construct.set` ハンドラーによって処理されます。フロー ローダーは `set` を標準ステップ タイプとして解釈しますが、実行はコンストラクトを介して行われます。 `set` コンストラクトが登録されていない場合、このステップはスキップされます。

#### フロー (サブフロー呼び出し)

```yaml
- id: run_sub_pipeline
  phase: main
  priority: 50
  type: flow
  flow: sub_flow_id
  args:
    param1: "${ctx.value}"
  output: sub_result
```

`flow` タイプは、別のフローをサブフローとして呼び出します。再帰呼び出し (循環参照) は自動的に検出され、エラーが発生します。サブフローのコンテキストが親からディープコピーされ、`args`で指定された値が追加されます。

#### 関数 (Capability 関数呼び出し)

```yaml
- id: read_store
  phase: main
  priority: 50
  type: function
  function: store.get
  input:
    store_id: "my_store"
    key: "${ctx.key}"
  output: store_result
```

`function` タイプは、`capability_executor` を介して FunctionRegistry に登録された関数を実行します。 `function` フィールドに `permission_id` (たとえば、`store.get`) を指定します。実行するには、対応する Capability Grant が必要です。

|フィールド |必須 |説明 |
|-----------|------|------|
| `type` | ✅ | `function` |
| `function` | ✅ |実行する関数のpermission_id (例: `store.get`、`docker.run`) |
| `input` |任意 |関数の引数（変数展開可能） |
| `output` |オプション |出力先コンテキストキー |
| `vocab_normalize` |オプション | `true` の場合、vocab は解く前に `function` の値を正規化します。

### 変数の展開

`${ctx.key}` を使用してコンテキスト内の値を参照できます。ネストされた参照 (`${ctx.user.id}`) も可能です。参照が存在しない場合は`null`となります。

### スケジュール実行

フローに`schedule`フィールドを追加することで定期的な実行が可能になります。

#### cron 式 (5 フィールド: 分、時、日、月、曜日)

```yaml
flow_id: daily_cleanup
schedule:
  cron: "0 0 * * *"

phases:
  - main
steps:
  # ...
```

#### 間隔 (秒指定、最小 10 秒)

```yaml
flow_id: health_check
schedule:
  interval: 30

phases:
  - main
steps:
  # ...
```

cron 式は、`*`、`*/N`、数値、カンマ区切り、範囲 (`N-M`)、および range+step (`N-M/S`) をサポートします。スケジューラは 10 秒ごとにティック単位で評価されるため、cron の精度は分単位になります。同じフローの重複実行は自動的に防止されます。

### フロー制御プロトコル

ブロックの戻り値で `__flow_control` キーを返すことで、フローの実行を制御できます。

#### 流れの中断

```python
def run(input_data, context=None):
    if not input_data.get("valid"):
        return {"__flow_control": "abort", "reason": "Invalid input"}
    return {"result": "ok"}
```

`{"__flow_control": "abort", "reason": "..."}` を返すと、それ以上のステップを実行せずにフローが中断されます。一時停止の理由は診断に記録されます。

> 現在、`__flow_control` は `"abort"` のみをサポートしています。他の値は無視されます。

---

## フロー → HTTP レスポンスのマッピング

Pack の `routes.json` で定義されたエンドポイントが HTTP リクエストを受信すると、Pack API サーバー (`pack_api_server.py`) が対応するフローを実行し、結果を HTTP レスポンスに変換して返します。

### 応答変換の仕組み

現在の実装では、フローの実行結果 (`outputs`) は **常に JSON 形式で返されます**。応答は `APIResponse` データ クラスを介して生成されます。

```python
@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
```

フローが正常に実行された場合:

```json
{
  "success": true,
  "data": { "...Flow outputs がここに入る..." },
  "error": null
}
```

フローの実行が失敗した場合:

```json
{
  "success": false,
  "data": null,
  "error": "エラーメッセージ"
}
```

### ステータスコード

Pack API サーバーの `_send_response` は、次の HTTP ステータス コードを使用します。

|ステータス |ステータスコード |
|------|-----------------|
|フローの実行が成功しました | `200 OK` |
|認証失敗 | `401 Unauthorized` |
|無効な入力 | `400 Bad Request` |
|ルートが見つかりません | `404 Not Found` |
|内部エラー | `500 Internal Server Error` |

### ヘッダー

次のヘッダーが応答に自動的に追加されます。

|ヘッダー |値 |状態 |
|---------|-----|------|
| `Content-Type` | `application/json; charset=utf-8` |常に許可されます |
| `Access-Control-Allow-Origin` |オリジンからのリクエスト | CORS 許可リストと一致します |
| `Vary` | `Origin` | CORSヘッダーを追加する場合 |

### 特殊キーによる制御

`_status_code`、`_headers`、`_body` などの特殊キーを使用した HTTP 応答の直接制御は、現時点では**サポートされていません**。フロー出力は常に `APIResponse` の `data` フィールドに保存され、`application/json` 形式で返されます。

カスタム ステータス コードまたはヘッダー コントロールが必要な場合は、[HTTP ステータス コード コントロール](#httpステータスコード制御) を参照してください。

---

## フロー修飾子

既存のフローに後から関数を挿入するための仕組みです。

### 配置パス

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/`

### 例

```yaml
# user_data/shared/flows/modifiers/add_logging.modifier.yaml

modifier_id: add_logging
target_flow_id: ai_response
phase: postprocess
priority: 90
action: inject_after
target_step_id: format_output

step:
  id: log_response
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log_ai_response.py
  input:
    response: "${ctx.response}"
```

### 利用可能なアクション

|アクション |説明 |
|--------|------|
| `inject_before` |指定したステップの前に挿入 |
| `inject_after` |指定したステップの後に挿入 |
| `append` |フェーズの最後に追加 |
| `replace` |指定されたステップを置き換える |
| `remove` |指定したステップを削除 |

> **フェーズ制約**: モディファイアの `phase` は、ターゲット フローの `phases` リストに含まれている必要があります。存在しないフェーズを指定した場合、モディファイアはスキップされます。

> **適用順序**: モディファイアはフェーズ → 優先順位 → modifier_id の順に並べ替えられ、決定的に適用されます。同じ挿入ポイントに複数のモディファイアが存在する場合 (`inject_before` / `inject_after` から同じ `target_step_id`)、インデックス シフトによる非決定性を防ぐために、優先順位 → step.id → modifier_id の順で一括挿入されます。 `replace` / `remove` は挿入/追加の前に適用されます。

### ワイルドカード target_flow_id

`target_flow_id` でワイルドカード パターンを使用して、モディファイアを複数のフローに同時に適用できます。

|パターン |意味 |
|----------|------|
| `*` |すべてのフローに適用 |
| `my_pack.*` | `my_pack.` で始まるすべてのフローに適用されます。

マッチングにはPythonの`fnmatch`を使用します。

```yaml
modifier_id: global_logging
target_flow_id: "*"
phase: postprocess
priority: 99
action: append
step:
  id: global_log
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log.py
```

### には条件が必要です

```yaml
requires:
  interfaces:
    - "ai.client"
  capabilities:
    - "tool_support"
```

条件が満たされない場合、モディファイアはスキップされます。

---

## ネットワークアクセス

### 概要

パックは Docker `--network=none` 内で分離されており、外部と直接通信することはできません。外部通信にはネットワーク許可が必要であり、すべてのリクエストは出力プロキシ (UDS ソケット) を経由します。

### ブロック内の HTTP リクエスト

```python
def run(input_data, context=None):
    http_request = context.get("http_request")
    if not http_request:
        return {"error": "http_request not available"}

    result = http_request(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": "Bearer ...",
            "Content-Type": "application/json"
        },
        body='{"model": "gpt-4", "messages": [...]}',
        timeout_seconds=30.0
    )

    if result["success"]:
        return {"data": result["body"]}
    else:
        return {"error": result["error"]}
```

> **タイムアウト制限**: `timeout_seconds` の最大値は 120 秒です。 120 を超える値は 120 秒に切り捨てられます。この制限は、`rumi_syscall` と `rumi_capability` の両方に適用されます。

### アクセスの可用性を事前確認する

```python
def run(input_data, context=None):
    check = context.get("network_check")
    result = check("api.openai.com", 443)

    if not result["allowed"]:
        return {"error": result["reason"]}

    # 通信可能
```

### 助成金の受け取り方法

ユーザーまたはオペレーターによって API 経由で付与されます。詳細については、[operations.md](./operations.md)の「ネットワーク権限管理」を参照してください。

---

## context["http_request"] 詳細仕様

`python_file_call` の `run(input_data, context)` で渡される `context["http_request"]` は、Pack コードが外部 HTTP 通信を行うための唯一の手段です。

### 関数のシグネチャ

```python
def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    ...
```

### パラメータ

|パラメータ |タイプ |デフォルト |説明 |
|------------|-----|-----------|------|
| `method` | `str` | (必須) | HTTPメソッド。 `GET`、`POST`、`PUT`、`DELETE`、`PATCH`、`HEAD` |
| `url` | `str` | (必須) |リクエストするための完全な URL |
| `headers` | `dict[str, str] \| None` | `None` | HTTP リクエストヘッダ |
| `body` | `str \| None` | `None` |リクエストの本文（文字列）。 JSON を送信するときは、`json.dumps()` 文字列 | を渡します。
| `timeout_seconds` | `float` | `30.0` |タイムアウト秒数。最大 `120.0` 秒に制限 |

### 戻り値

成功時:

```python
{
    "success": True,
    "status_code": 200,          # int: HTTPステータスコード
    "headers": {"Content-Type": "application/json", ...},  # dict: レスポンスヘッダー
    "body": "...",               # str: レスポンスボディ
    "latency_ms": 123.4,         # float: 所要時間（ミリ秒）
    "redirect_hops": 0,          # int: リダイレクト回数
    "bytes_read": 1024,          # int: 読み取りバイト数
    "final_url": "https://...",  # str: 最終URL（リダイレクト後）
}
```

失敗時:

```python
{
    "success": False,
    "error": "エラーメッセージ",     # str: エラー内容
    "error_type": "timeout",       # str: エラー種別
}
```

### error_type リスト

|エラーの種類 |説明 |
|------------|------|
| `socket_not_found` |出力プロキシ ソケットが見つかりません |
| `permission_denied` |ソケットにアクセスする権限がありません |
| `connection_refused` | Egress プロキシへの接続が拒否されました |
| `timeout` |リクエストがタイムアウトしました |
| `syscall_error` |プロトコル レベルのエラー |
| `json_decode_error` |応答の JSON 解析が失敗しました |
| `grant_denied` |ネットワーク許可によりアクセスが拒否されました |

### UDS Egress プロキシ経由の通信

Pack コードからのすべての外部 HTTP 通信は、**UDS (Unix Domain Socket) Egress Proxy** を経由します。パックコードは直接ネットワーク通信を行うことができません。

コミュニケーションの流れ：

```
Pack コード (run関数)
  → context["http_request"]()
    → UDS ソケット (/run/rumi/egress/packs/{pack_id}.sock)
      → Egress Proxy (Kernel 側)
        → Network Grant Manager でアクセス許可を検証
          → 許可されていれば外部 HTTP リクエストを実行
          → 拒否されていれば grant_denied エラーを返却
```

> ソケットのパスは `RUMI_EGRESS_SOCK_DIR` 環境変数で変更できます。デフォルトは`/run/rumi/egress/packs`です。

### コンテナモードとホストモードの違い

|アイテム |コンテナモード (厳密) |ホストモード (寛容) |
|------|--------------------------|---------------------------|
|ネットワーク | `--network=none` (完全隔離) |ホストネットワークを使用する |
|通信経路 | UDS ソケット経由のみ | UDS ソケット経由 (ヘルパー関数経由) |
|ソケットパス | `/run/rumi/egress/packs/{pack_id}.sock` (コンテナマウント内) | `{RUMI_EGRESS_SOCK_DIR}/{pack_id}.sock` |
|認可が承認されました |出力プロキシが検証されました |出力プロキシが検証されました |
|セキュリティ | Docker 隔離 + UDS の制限 |警告付きで実行 (運用環境では推奨されません) |

コンテナ モード (`RUMI_SECURITY_MODE=strict`) では、Docker コンテナは `--network=none` で起動されるため、UDS ソケット以外の通信手段はありません。ホストモード(`RUMI_SECURITY_MODE=permissive`)はDockerなしで動作しますが、`context["http_request"]`もEgress Proxyを経由するため、Network Grantによる制御が有効です。

### 使用例

```python
def run(input_data: dict, context: dict) -> dict:
    # GET リクエスト
    result = context["http_request"](
        method="GET",
        url="https://api.example.com/data",
        headers={"Accept": "application/json"},
        timeout_seconds=10.0,
    )

    if not result["success"]:
        return {"error": result["error"]}

    return {"status": result["status_code"], "body": result["body"]}
```

```python
def run(input_data: dict, context: dict) -> dict:
    import json

    # POST JSON リクエスト
    result = context["http_request"](
        method="POST",
        url="https://api.example.com/items",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"name": input_data.get("name")}),
        timeout_seconds=15.0,
    )

    if not result["success"]:
        return {"error": result["error"], "error_type": result.get("error_type")}

    return {"created": True, "response": result["body"]}
```

---

## シークレットの使用 (パックから)

パックは、`secrets.get` 機能を使用してシークレット (API キーなど) を取得します。オペレーターがシークレットを登録し、グラントを付与すると利用可能になります。

### 使用例

```python
import rumi_capability

result = rumi_capability.call("secrets.get", args={"key": "OPENAI_API_KEY"})
if result["success"]:
    api_key = result["output"]["value"]
else:
    # "Access denied or secret not found"
    error = result["output"]["error"]
```

### アクセス制御

`secrets.get` の許可では、`grant_config.allowed_keys` でアクセス可能なキーを明示的に指定する必要があります。 `allowed_keys` が空または指定されていない場合、すべてのキーへのアクセスが拒否されます (フェールクローズ)。

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "my_pack",
    "permission_id": "secrets.get",
    "config": {"allowed_keys": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]}
  }'
```

### 重要な制約

- `get`はケイパビリティ経由でのみ入手可能です。シークレット値を直接再表示する API は存在しません
- レート制限は`secrets.get`に適用されます(デフォルトは60回/分/パック、環境変数`RUMI_SECRET_GET_RATE_LIMIT`で変更可能、スライディングウィンドウ方式)
- 値がログ、監査、例外メッセージに含まれることはありません
・エラーメッセージからはキーが存在するかどうか判断できない（「アクセスが拒否された、またはシークレットが見つかりません」で統一）

---

## 機能の使用

パックが機能ハンドラーを使用するには (ファイル システムの読み取り、外部ツールの実行など)、パックに適切な権限付与が付与されている必要があります。

### 信託と助成金の関係

機能には 2 つのレベルの承認が必要です。

1. **信頼登録** (ハンドラー認可): ハンドラーのコード (sha256) を信頼できるものとして登録します。
2. **Grant** (権限付与): 承認されたハンドラーの権限をパックに付与します。

```
handler.py が信頼される（Trust 登録）
    ↓
Pack に permission が付与される（Grant 付与）
    ↓
Pack が capability を使用可能
```

トラストを登録しても、助成金がなければ利用することはできません。逆に、グラントがあってもトラストが登録されていないハンドラは実行できません。

### ケイパビリティを呼び出す方法

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})
if result["success"]:
    content = result["output"]
else:
    error = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
```

### 組み込み機能ハンドラー

次の機能ハンドラーはコア ランタイムに含まれており、信頼登録なしで使用できます (別途許可が必要です)。

|許可ID |ハンドラーID |説明 |リスク |
|---------------|-----------|------|------|
| `secrets.get` | `core.secrets.get` |シークレット値を取得 |高い |
| `store.get` | `core.store.get` |ストアから値を読み取る |低い |
| `store.set` | `core.store.set` |ストアへの値の書き込み |中 |
| `store.delete` | `core.store.delete` |ストアから値を削除する |中 |
| `store.list` | `core.store.list` |ストア内のキーのリストを取得 |低い |
| `store.batch_get` | `core.store.batch_get` |ストアからの一括取得（最大100キー） |低い |
| `store.cas` | `core.store.cas` | Store Compare-And-Swap (楽観的排他制御) |中 |
| `pack.inbox.send` | `core.communication.send` | JSON メッセージを他のパック コンポーネントの受信箱に送信する |中 |
| `pack.update.propose_patch` | `core.communication.propose_patch` |他のパックへのファイル変更を提案する (ステージング作成、自動適用なし) |高い |
| `flow.run` | `core.flow.run` |同期フローツーフロー呼び出し |中 |
| `docker.run` | `core.docker.run` | Dockerコンテナの実行 | — |
| `docker.exec` | `core.docker.exec` | Dockerコンテナ内でのコマンド実行 | — |
| `docker.stop` | `core.docker.stop` | Dockerコンテナの停止 | — |
| `docker.logs` | `core.docker.logs` | Dockerコンテナログ取得 | — |
| `docker.list` | `core.docker.list` | Dockerコンテナリスト | — |

### 助成金 助成金

許可は、API を使用してユーザーまたはオペレーターによって付与されます。詳細については、[operations.md](./operations.md)の「能力付与管理」を参照してください。

```bash
# 例: store.get の Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["my_store"]}}'
```

### 許可設定 (grant_config)

助成金には、`config` で制限を設定できます。権限により設定が異なります。

|許可ID | Grant_config キー |説明 |
|---------------|-------------------|------|
| `secrets.get` | `allowed_keys` |アクセス可能なキー名のリスト (必須、空の場合は完全に拒否) |
| `store.get/set/delete/list` | `allowed_store_ids` |アクセス可能なストア ID のリスト (必須、空の場合は完全に拒否されます) |
| `store.set` | `max_value_bytes` |最大書き込みサイズ (バイト、デフォルトは 1MB) |

`allowed_keys` / `allowed_store_ids` はフェールクローズされます。リストが空であるか指定されていない場合は、すべてのアクセスが拒否されます。

### エラー処理

Capability 呼び出しが失敗すると、`success: False` を含む辞書が返されます。

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})

if not result.get("success", False):
    error_type = result.get("error_type", "unknown")

    if error_type == "grant_denied":
        # Grant が付与されていない
        pass
    elif error_type == "trust_denied":
        # handler が信頼されていない
        pass
    elif error_type == "handler_not_found":
        # handler が存在しない
        pass
    elif error_type == "execution_error":
        # handler 実行中のエラー
        pass
    elif error_type == "timeout":
        # タイムアウト
        pass
```

|エラーの種類 |説明 |
|------------|------|
| `grant_denied` |パックには権限の付与がありません |
| `trust_denied` |ハンドラの sha256 が Trust Store に登録されていません |
| `handler_not_found` |指定されたpermission_idに対応するハンドラーが存在しません。
| `execution_error` |ハンドラーの実行中にエラーが発生しました |
| `timeout` |実行がタイムアウトしました |
| `socket_not_found` |機能ソケットが見つかりません |

---

## ストア API (機能経由)

### 概要

ストアは、パック間で共有できるキーと値のストアです。ストア操作は機能を通じて実行されます。オペレーターがパックに機能付与を付与すると、アクセスが有効になります。

### 利用可能なpermission_id

|許可ID |説明 |引数 |
|---------------|------|------|
| `store.get` |ストアから値を読み取る | `store_id`、`key` |
| `store.set` |ストアに値を書き込む | `store_id`、`key`、`value` |
| `store.delete` |ストアから値を削除 | `store_id`、`key` |
| `store.list` |ストア内のキーのリストを取得 | `store_id`、`prefix` (オプション) |

### 使用例

```python
import rumi_capability

# 値の書き込み
result = rumi_capability.call("store.set", args={
    "store_id": "my_store",
    "key": "users/user_001",
    "value": {"name": "Alice", "role": "admin"}
})

# 値の読み取り
result = rumi_capability.call("store.get", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
if result["success"]:
    output = result["output"]
    if output.get("success"):
        user = output["value"]

# キー一覧
result = rumi_capability.call("store.list", args={
    "store_id": "my_store",
    "prefix": "users/"
})
```

> `store.list` の `output` には、`success` (ブール値) と `keys` (キー名の配列) が含まれています。

```python
# 値の削除
result = rumi_capability.call("store.delete", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
```

### 付与設定

`store.*` の助成金には、`grant_config` で制限を設定できます。

| Grant_config キー |説明 |デフォルト |
|-------------------|------|-----------|
| `allowed_store_ids` |アクセスを許可するstore_idのリスト | `[]` (リストが空の場合、すべてのストアへのアクセスが拒否されます。アクセスするには Store_id を明示的に指定する必要があります) |
| `max_value_bytes` | `store.set` 最大サイズ (バイト) | 1MB (1048576) |

`allowed_store_ids` はフェールクローズされています。許可の作成時に `allowed_store_ids` を指定しないか、空のリスト `[]` を指定した場合、その許可に対するすべてのストアへのアクセスは拒否されます。パックがストアにアクセスするには、オペレーターがリストに明示的に store_id を追加する必要があります。

### ストアを作成する

ストアの作成は、運用 API を使用して行われます。

```bash
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "my_store", "root_path": "user_data/stores/my_store"}'
```

> **store_id 制約**: `store_id` は `^[a-zA-Z0-9_-]{1,64}$` と一致する必要があります。

### 組み込み機能ハンドラーのリスト

次の機能ハンドラーはコア ランタイムに含まれており、信頼登録なしで使用できます (別途許可が必要です)。

|許可ID |ハンドラーID |説明 |リスク |
|---------------|-----------|------|------|
| `secrets.get` | `core.secrets.get` |シークレット値を取得 |高い |
| `store.get` | `core.store.get` |ストアから値を読み取る |低い |
| `store.set` | `core.store.set` |ストアへの値の書き込み |中 |
| `store.delete` | `core.store.delete` |ストアから値を削除する |中 |
| `store.list` | `core.store.list` |ストア内のキーのリストを取得 |低い |
| `store.batch_get` | `core.store.batch_get` |ストアからの一括取得（最大100キー） |低い |
| `store.cas` | `core.store.cas` | Store Compare-And-Swap (楽観的排他制御) |中 |
| `pack.inbox.send` | `core.communication.send` | JSON メッセージを他のパック コンポーネントの受信箱に送信する |中 |
| `pack.update.propose_patch` | `core.communication.propose_patch` |他のパックへのファイル変更を提案する (ステージング作成、自動適用なし) |高い |
| `flow.run` | `core.flow.run` |同期フローツーフロー呼び出し |中 |
| `docker.run` | `core.docker.run` | Dockerコンテナの実行 | — |
| `docker.exec` | `core.docker.exec` | Dockerコンテナ内でのコマンド実行 | — |
| `docker.stop` | `core.docker.stop` | Dockerコンテナの停止 | — |
| `docker.logs` | `core.docker.logs` | Dockerコンテナログ取得 | — |
| `docker.list` | `core.docker.list` | Dockerコンテナリスト | — |

---

## パック間の連携パターン

### 共有フローによる配線

`user_data/shared/flows/`に配置されたフローを使用して、複数のパックのブロックを接続できます。パックはお互いのことを知る必要はありません。

```yaml
# user_data/shared/flows/ai_pipeline.flow.yaml
flow_id: ai_pipeline
phases:
  - prepare
  - generate
  - postprocess

steps:
  - id: load_capabilities
    phase: prepare
    priority: 50
    type: python_file_call
    owner_pack: capability_provider
    file: blocks/load_capabilities.py
    output: capabilities

  - id: generate
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      capabilities: "${ctx.capabilities}"
    output: response
```

### ストア経由のデータ配信

ストアを使用して、異なるフローで動作するパック間でデータを共有します。

```python
# Pack A: データを Store に書き込む
import rumi_capability

rumi_capability.call("store.set", args={
    "store_id": "shared_data",
    "key": "latest_result",
    "value": {"score": 0.95, "text": "..."}
})
```

```python
# Pack B: Store からデータを読み取る
import rumi_capability

result = rumi_capability.call("store.get", args={
    "store_id": "shared_data",
    "key": "latest_result"
})
if result["success"]:
    data = result["output"]["value"]
```

---

## lib（インストール/アップデート）

### 概要

これは、パックの初期化または更新時に 1 回だけ実行されるスクリプトです。通常は実行されません。

### ファイル構造

```
ecosystem/<pack_id>/backend/lib/
├── install.py    # 初回導入時に実行
└── update.py     # ハッシュ変更時に実行（なければ install.py が実行される）
```

### install.py の例

```python
def run(context=None):
    pack_id = context.get("pack_id") if context else "unknown"
    data_dir = context.get("data_dir") if context else None

    # data_dir 内に初期設定ファイルを作成
    if data_dir:
        import json, os
        config_path = os.path.join(data_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump({"initialized": True}, f)

    return {"status": "installed"}
```

### コンテキストによって提供される情報

|キー |説明 |
|------|------|
| `pack_id` |パックID |
| `lib_type` | `"install"` または `"update"` |
| `ts` |タイムスタンプ |
| `lib_dir` | lib ディレクトリ パス (コンテナ内: `/lib`) |
| `data_dir` |書き込み可能なディレクトリ (コンテナ内: `/data`、ホスト: `user_data/packs/{pack_id}/`) |

### セキュリティ上の制約

厳密モードでは、Docker コンテナ内で分離して実行されます。 `--network=none`、`--read-only`。 `/data`(=`user_data/packs/{pack_id}/`)のみ書き込み可能です。

---

## pip 依存関係 (requirements.lock)

### 概要

パックが PyPI パッケージに依存している場合は、`requirements.lock` を含めます。

### 配置パス

以下の順番で検索しました。

1. `<pack_subdir>/requirements.lock`
2. `<pack_subdir>/backend/requirements.lock` (互換)

### フォーマット

`NAME==VERSION` 行のみが許可されます。コメント行と空白行は許可されます。

```
requests==2.31.0
flask==3.0.0
```

以下は禁止されています: `-e`、`git+`、`http://`、`https://`、`file:`、`../`、`/`、`--`のオプション行、`@`の直接参照。

### パックコードからの使用

承認してインストールしたら、通常どおり `import` を実行するだけです。

```python
import requests  # pip で導入された依存

def run(input_data, context=None):
    resp = requests.get("https://api.example.com/data")
    return {"data": resp.json()}
```

実行コンテナでは、サイト パッケージが `/pip-packages:ro` としてマウントされ、`PYTHONPATH` に追加されます。

### 承認を得る方法

ユーザーまたはオペレーターは API 経由で承認します。詳細については、[operations.md](./operations.md)の「pip 依存関係ライブラリ管理」を参照してください。

---

## 権限.json

パックに必要な権限を宣言するファイル。

```json
{
  "pack_id": "my_pack",
  "permissions": [
    {
      "type": "network",
      "domains": ["api.example.com"],
      "ports": [443],
      "reason": "外部 API にアクセスするため"
    }
  ]
}
```

Permissions.json は宣言型であり、実行時に強制されません。実際のアクセス制御は、Capability Grants と Network Grants を通じて行われます。このファイルは、ユーザーへの情報提供 (このパックに必要な権限) を目的としています。

---

## 機能ハンドラーを含める

パックが機能ハンドラーを提供する場合、次の規則に従います。

### 配置

```
ecosystem/<pack_id>/
└── backend/
    └── share/
        └── capability_handlers/
            └── <slug>/
                ├── handler.json
                └── handler.py
```

パックの `pack_subdir` (通常は `ecosystem/<pack_id>/backend/`) の下の `share/capability_handlers/<slug>/` に配置します。

### ハンドラー.json

```json
{
  "handler_id": "fs_read_handler",
  "permission_id": "fs.read",
  "entrypoint": "handler.py:execute",
  "description": "ファイルシステム読み取り handler",
  "risk": "ファイルシステムへの読み取りアクセスを提供"
}
```

|フィールド |必須 |説明 |
|-----------|------|------|
| `handler_id` | ✅ |ハンドラーの一意の識別子 |
| `permission_id` | ✅ |要求された権限 ID |
| `entrypoint` | ✅ |実行エントリポイント (例: `handler.py:execute`) |
| `description` |オプション |説明 |
| `risk` |オプション |リスクの説明 |

候補はスキャンによって検出され、ユーザーによって承認され、`user_data/capabilities/handlers/<slug>/` にコピーされます。 Approve は Trust (sha256 ホワイトリスト) のみを登録します。Grant は別途必要です。

> 上記は古い方法（互換性あり）です。新しいパックでは次の機能/メソッドを推奨します。

### 関数/メソッド (推奨)

パックが機能機能を提供する場合は、それを `functions/` ディレクトリに配置します。

#### 配置

```
ecosystem/<pack_id>/
└── backend/
    └── functions/
        └── <function_id>/
            ├── manifest.json
            └── main.py
```

#### マニフェスト.json

```json
{
  "function_id": "get",
  "description": "Read a value from a Store by key.",
  "requires": ["store.get"],
  "caller_requires": [],
  "host_execution": true,
  "tags": ["store", "read"],
  "risk": "low",
  "vocab_aliases": ["store.get"],
  "input_schema": {
    "type": "object",
    "required": ["store_id", "key"],
    "properties": {
      "store_id": { "type": "string" },
      "key": { "type": "string" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "success": { "type": "boolean" },
      "value": { "description": "The stored JSON value" }
    }
  },
  "calling_convention": "block"
}
```

|フィールド |必須 |説明 |
|-----------|------|------|
| `function_id` | ✅ |関数識別子 |
| `description` |オプション |機能説明 |
| `requires` | ✅ |この関数を実行するために必要な許可 ID のリスト (例: `["store.get"]`) |
| `caller_requires` |オプション |呼び出し元に要求する追加の権限のリスト |
| `host_execution` |オプション | `true` の場合、コンテナではなくホスト プロセスで実行します。
| `tags` |オプション |分類タグ一覧 |
| `risk` |オプション |リスクレベル (`low`、`medium`、`high`)。 docker type | など一部の関数では省略されています。
| `vocab_aliases` |オプション |語彙の正規化に使用されるエイリアスのリスト |
| `input_schema` |オプション |入力 JSON スキーマ |
| `output_schema` |オプション |出力 JSON スキーマ |
| `grant_config` |オプション | Grant のデフォルト設定 (Docker システムで使用) |
| `calling_convention` |オプション |呼び出し規約。 `block` (デフォルト、core_pack 標準) = `execute(context, args)` パターン |

> **注意**: `permission_id` フィールドは、manifest.json には存在しません。 `requires` 配列を使用して権限を指定します。

#### main.py

```python
def execute(context: dict, args: dict) -> dict:
    """
    Args:
        context: 実行コンテキスト
            - grant_config: Grant 設定（allowed_store_ids 等）
        args: 入力引数（manifest.json の input_schema に対応）

    Returns:
        JSON 互換の dict
    """
    store_id = args.get("store_id", "")
    key = args.get("key", "")

    # ... 処理 ...

    return {"success": True, "value": result}
```

`calling_convention` が `block` (デフォルト) の場合、エントリ ポイントは `execute(context, args)` です。 `context`には`grant_config`などの実行情報が含まれており、`args`にはフローステップの`input`で指定した値が渡されます。

---

## 語彙/コンバーター (上級)

> 通常の Pack 開発では使用する必要はありません。互換性吸収のための高度な機能。

### 語彙.txt

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

同じ行に書かれた単語は同義語として扱われます。

###コンバータ

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

---

## コンポーネント (詳細)

コンポーネントは`components/{component_id}/manifest.json`を持つユニットであり、ライフサイクル管理(セットアップなど)に使用されます。 `python_file_call`ではコンポーネントを特別に扱っていないため、`file`フィールドには相対パスを指定してください。

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

### setup.pyの基本パターン

コンポーネントの初期化処理は`components/{component_id}/setup.py`で説明されています。

```python
# ecosystem/my_pack/backend/components/my_component/setup.py

def setup(context=None):
    """
    Component 初期化時に呼ばれる。

    Args:
        context: 実行コンテキスト
            - interface_registry: InterfaceRegistry
            - event_bus: EventBus
            - diagnostics: Diagnostics
            - install_journal: InstallJournal

    Returns:
        任意の値（diagnostics に記録される）
    """
    ir = context.get("interface_registry") if context else None
    if ir:
        ir.register("my_component.ready", True)
    return {"status": "initialized"}
```

セットアップは起動時に`kernel:component.load`ステップで実行されます。

---

## パック固有のエンドポイント (routes.json)

### 概要

パックには、独自のエンドポイントを HTTP API サーバーに登録するための `routes.json` を含めることができます。受信したリクエストは指定されたフローを実行し、結果をレスポンスとして返します。

### 配置パス

§るみ§0§

### ルート.json 形式

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/api/my_pack/generate",
      "flow_id": "my_pack.generate",
      "description": "テキスト生成エンドポイント"
    },
    {
      "method": "GET",
      "path": "/api/orgs/{org_id}/tasks/{task_id}",
      "flow_id": "my_pack.get_task",
      "description": "タスク取得（パスパラメータ付き）"
    }
  ]
}
```

### パスパラメータ

パス パラメーターは、`{param}` 表記を使用して定義できます。パス パラメーターの値は、フローの `inputs` に自動的に含まれます。

例: `/api/orgs/{org_id}/tasks/{task_id}` をリクエストした場合、`inputs.org_id` および `inputs.task_id` にはそれぞれの値が設定されます。

### GET クエリパラメータ

GET リクエストのクエリ パラメータも `inputs` に含まれています。

### 生のボディ/ヘッダーを取得する

Flow の `inputs` には、次の特殊キーも含まれています。

|キー |説明 |
|------|------|
| `_raw_body` |リクエストボディのbase64エンコード値 |
| `_headers` |リクエストヘッダーの辞書 |
| `_method` | HTTP メソッド (GET、POST など) |
| `_path` |リクエストパス |

### ルートをリロードする

```bash
curl -X POST http://localhost:8765/api/routes/reload \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 登録したルートを確認する

```bash
curl http://localhost:8765/api/routes \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## HTTPステータスコード制御

### 現在の仕様

現在の Pack API サーバーの実装では、**Pack が Pack の `routes.json` エンドポイントから返される HTTP ステータス コードを直接制御することはできません。

フローの出力に `_status_code` などの特殊キーを含めた場合でも、応答の `data` フィールドに含まれるだけで、HTTP ステータス コードには反映されません。

### ステータスコード判定ロジック

Pack API サーバーは、次のロジックを使用してステータス コードを決定します。

|判決命令 |ステータス |ステータスコード |
|--------|------|-----------------|
| 1 |認証失敗 | `401` |
| 2 |入力検証の失敗 | `400` |
| 3 |ルートが見つかりません | `404` |
| 4 |フローの実行が成功しました | `200` (修正) |
| 5 |フローの実行時にエラー辞書が返されました | `200` (データにエラーが含まれていますが、HTTP は 200) |
| 6 |フロー実行中に例外が発生する | `500` |

これは、フローが正常に完了して `{"error": "not found"}` を返した場合でも、HTTP ステータス コードは `200 OK` になることを意味します。

### 推奨パターン

現在の制約では、応答本文の `success` フィールドと `error` フィールドを使用して、クライアントにエラーを伝えます。

```python
def run(input_data: dict, context: dict) -> dict:
    item_id = input_data.get("id")
    if not item_id:
        return {"error": "missing id", "error_code": "MISSING_ID"}

    # ... 処理 ...

    if not found:
        return {"error": "item not found", "error_code": "NOT_FOUND"}

    return {"item": item_data}
```

クライアント側では`data.error`の有無で成功/失敗が決まります。

### 将来のサポート予定

将来のバージョンでは、フロー出力の特殊キー (`_status_code`、`_headers` など) を認識し、HTTP レスポンスに反映する機能の追加を検討しています。

---

## エラー処理のベスト プラクティス

### python_file_callのrun()で例外が発生した場合

`run()` 関数内でキャッチされない例外が発生すると、実行エンジンは次のことを行います。

**コンテナ モード**: Docker プロセスはゼロ以外の終了コードで終了し、stderr の内容がエラー メッセージとして記録されます。 `ExecutionResult`の`success`は`False`となり、`error_type`は`"container_execution_error"`となります。

**ホスト モード (許可)**: 例外は `ThreadPoolExecutor` の `Future` から伝播し、同様に `ExecutionResult` の `success` が `False` になります。

いずれの場合も、カーネルのハンドラ (`_h_python_file_call`) は `_kernel_step_status: "failed"` を返します。

### 推奨: Try-Except でラップしてエラー辞書を返す

例外をリークした場合、スタック トレースのみがログに記録され、呼び出し元のフローには有用な情報は渡されません。必ず Try-Except でラップし、構造化されたエラー情報を返してください。

```python
def run(input_data: dict, context: dict) -> dict:
    try:
        url = input_data["url"]
        result = context["http_request"](
            method="GET",
            url=url,
            timeout_seconds=input_data.get("timeout", 30),
        )

        if not result["success"]:
            return {
                "error": result["error"],
                "error_type": result.get("error_type", "unknown"),
            }

        return {"data": result["body"], "status_code": result["status_code"]}

    except KeyError as e:
        return {"error": f"missing required field: {e}"}
    except Exception as e:
        return {"error": str(e), "error_type": type(e).__name__}
```

### フローステップが失敗した場合の動作

フロー内のステップが失敗したときの動作は、フロー定義の `defaults` およびステップごとの `on_error` 設定によって決まります。

|設定 |行動 |
|------|------|
| `defaults.fail_soft: true` (デフォルト) |ステップの失敗を記録し、次のステップに進みます。
| `defaults.fail_soft: false` |ステップが失敗したときにフロー全体を中断する |
| `on_error.action: "abort"` |このステップが失敗した場合はフローを中止します。
| `on_error.action: "continue"` |このステップが失敗しても続行します。
| `on_error.action: "disable_target"` |ターゲットを無効にして続行 |

フロー レベルのエラー ハンドラーが InterfaceRegistry に `flow.error_handler` として登録されている場合、ステップ例外が発生したときにそのハンドラーが呼び出されます。エラー ハンドラーは、`"abort"` (中止)、`"retry"` (再試行)、またはその他の何か (続行) を返すことによって動作を制御できます。

###capability.call() が失敗した場合の戻り値の処理方法

`rumi_capability` モジュール経由で Capability を呼び出すと、失敗時に `success: False` を含む辞書が返されます。

```python
import rumi_capability

result = rumi_capability.call(
    "store.get",
    args={"store_id": "my_store", "key": "my_key"},
)

if not result.get("success", False):
    # エラー処理
    error_msg = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
    return {"error": error_msg, "error_type": error_type}

# 成功時の処理
value = result.get("output", {}).get("value")
```

機能呼び出しが失敗する考えられる理由は次のとおりです。

|エラーの種類 |説明 |
|------------|------|
| `approval_denied` |機能の使用は許可されていません |
| `grant_denied` |能力付与が付与されていません |
| `trust_denied` |トラスト ストアの検証に失敗しました |
| `handler_not_found` |指定された機能ハンドラーは存在しません。
| `execution_error` |ハンドラー | の実行中にエラーが発生しました。
| `timeout` |実行がタイムアウトしました |
| `socket_not_found` |機能ソケットが見つかりません |

Try-Except を使用する代わりに、戻り値の `success` フィールドを使用してこれらのエラーをチェックすることをお勧めします。

---

---

## Flow Modifier 推奨パターン

Flow Modifier は強力な機能ですが、最初からすべてのアクションを使用しようとすると複雑になる可能性があります。まずは以下の2パターンから始めることをおすすめします。

### パターン 1: 追加 (フェーズの最後に追加)

これは最も安全で理解しやすいパターンです。既存のフローを変更せずに最後に処理を追加します。

```yaml
modifier_id: add_logging
target_flow_id: ai_response
phase: postprocess
priority: 90
action: append

step:
  id: log_response
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log_response.py
  input:
    response: "${ctx.response}"
```

使用する場合: ログ記録、監査、通知、後処理を追加します。

### パターン2: 置換(ステップ置換)

これは、既存のステップの実装を置き換えるパターンです。たとえば、AI クライアントを OpenAI から Anthropic に切り替えるときにこれを使用します。

```yaml
modifier_id: swap_ai_client
target_flow_id: ai_response
phase: generate
priority: 50
action: replace
target_step_id: call_openai

step:
  id: call_anthropic
  type: python_file_call
  owner_pack: anthropic_client
  file: blocks/generate.py
  input:
    user_input: "${ctx.user_input}"
  output: ai_output
```

使用する場合: 実装の置き換え、プロバイダーの切り替え

### inject_before / inject_after を使用する場合

inject_before / inject_after は、特定のステップの前後に処理を挿入したい場合に使用します。ただし、対象ステップのidに依存するため、フロー構造の変更には弱いです。次の場合にのみ使用を検討してください。

- 特定のステップの入力データを事前変換する必要がある場合 (inject_before)
- 特定のステップの出力データを後処理する必要がある場合 (inject_after)
・実行タイミングが遅すぎて追加できない場合

### 削除は最後の手段です

Remove は既存のステップを削除し、フローの動作を大幅に変更する可能性があります。通常は、replace を使用して代替実装を提供する方が安全です。

---

## ハンドラー API の分類

カーネルが提供するハンドラーには、「パック開発者向け」と「内部 API」の 2 種類があります。

### パック開発者 API

フロー定義内で直接使用できるハンドラーです。安定したインターフェイスが保証されます。

|ハンドラー |説明 |フローでの使い方 |
|---------|------|----------------|
| `python_file_call` | Python ファイルを実行する | `type: python_file_call` |
| `flow` |コールサブフロー | `type: flow` |
| `function` |能力機能の実行 | `type: function` |
| `set` |コンテキストで値を設定 | `type: set` |
| `handler` |登録されたハンドラーを直接呼び出す | `type: handler` |

### 内部 API (パック開発者は使用しません)

カーネルの内部操作に使用されるハンドラー。パック開発者はこれらを直接呼び出す必要はありません。

|カテゴリー |例 |説明 |
|---------|-----|------|
| `kernel:*` | `kernel:ctx.get`、`kernel:ctx.set` |カーネル内のコンテキスト操作 |
| `flow.hooks.*` | `flow.hooks.pre_step`、`flow.hooks.post_step` |フロー ライフサイクル フック |
| `flow.construct.*` | `flow.construct.set`、`flow.construct.if` |フロー構文の内部実装 |
| `component_phase:*` | `component_phase:setup`、`component_phase:startup` |コンポーネントのライフサイクル |

> **注意**: 内部 API は予告なく変更される場合があります。これらをパックのフロー定義から直接参照しないでください。

---

## 出力キーの命名規則 (詳細)

### カーネル内部キーの除外ルール

フローの実行結果が HTTP レスポンスとして返される場合、以下のプレフィックスで始まるキーは **カーネル内部キー**として自動的に除外されます。

|プレフィックス |説明 |
|---------------|------|
| `_flow_` |フロー制御情報 |
| `_kernel_` |カーネルステップメタデータ |
| `_step_out.` |ステップ出力内部リファレンス |
| `_current_step` |現在のステップ番号 |
| `_total_steps` |総ステップ数 |
| `_parent_flow` |親フロー情報 |
| `_principal_id` |実行者 ID |
| `_flow_control` |フロー制御信号 |
| `_error` |エラー情報 |
| `_flow_defaults` |フローのデフォルト値 |

### Pack 開発者が `_` プレフィックス キーを返した場合

上記のカーネル内部プレフィックスと**一致しない** `_` プレフィックス キー (例: `_debug`、`_my_internal`) は応答から除外されません。ただし、警告が記録されます。

```python
# この例では _debug は除外されず、レスポンスに含まれる（警告ログ付き）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_debug": {"raw_response": "..."},  # 警告ログが出るがレスポンスに残る
    }
```

### 推奨事項

- Pack 出力キーには `_` プレフィックスを使用しないことをお勧めします。
- デバッグ情報を含める場合は、`debug` や `metadata` などの通常のキー名を使用します。
- カーネル内部プレフィックス (例: `_flow_result`) と偶然一致するキー名は、意図せずに除外されるため、特に避ける必要があります。

```python
# ✅ 推奨
def run(input_data, context=None):
    return {
        "result": "ok",
        "debug_info": {"raw_response": "..."},
        "metadata": {"source": "my_pack", "version": "1.0"},
    }

# ⚠️ 非推奨（動作はするが警告ログが出る）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_debug": {"raw_response": "..."},
    }

# ❌ 避けるべき（Kernel 内部キーとして除外される）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_flow_result": "this will be silently removed",
        "_kernel_data": "this will also be removed",
    }
```


## 注意事項

- **InterfaceRegistry は内部 API です。 ** パックから直接 IR を操作しないでください。
- **外部通信は出力プロキシ経由で行う必要があります**。 `context["http_request"]`を使用します。
- **lib は `/data` にのみ書き込むことができます。 ** 他のパスへの書き込みは、`--read-only` により失敗します。
- **pack_identity を変更しないでください。 ** アップデート中に`pack_identity`が変更された場合、適用は拒否されます。
- **principal_id は、v1 の owner_pack によって強制的に上書きされます。 ** フロー定義やモディファイアに`principal_id`を指定した場合でも、実行時には`owner_pack`の値がプリンシパルとして使用されます。不一致が検出された場合、警告が監査ログに記録されます。
- **応答サイズ制限について**: Egress Proxy (`rumi_syscall`) および Capability Client (`rumi_capability`) の応答制限は 4MB です (`RUMI_MAX_RESPONSE_BYTES` で変更可能)。ただし、Capability Executor (サーバー側のサブプロセス実行) の応答制限は 1MB です。
- **store.set のデフォルト値のサイズ制限は 1MB です。 ** グラントの`grant_config.max_value_bytes`で変更可能。
- **FlowScheduler の最小間隔値は 10 秒です。 ** 10 秒未満を指定した場合、10 秒未満は切り上げられます。
- **フローの同時実行数のデフォルトは 10 です。** `RUMI_MAX_CONCURRENT_FLOWS` 環境変数を使用して変更できます。
- **機能の実行タイムアウト制限は 120 秒です。 ** `rumi_capability.call()`の`timeout_seconds`に120を超える値を指定しても120秒に制限されます。デフォルトは 30 秒です。

### ハードリンクはサポートされていません

Pack ディレクトリ (`ecosystem/<pack_id>/`) 内でのハード リンクの使用は **サポートされていません**。

#### 理由

Pack 認可/ハッシュ検証システムは、`Path.resolve()` で正規化されたファイル パスをキャッシュ キーとして使用します。シンボリック リンクは `resolve()` によって実際のパスに解決されるため、ソースと宛先は同じキャッシュ エントリに結合されます。一方、`resolve()`ではハードリンクは統一されていません(各パスエントリは独立しています)。したがって、同じ i ノードを指す複数のパスは別個のキャッシュ エントリとして扱われ、一方のパスを介したファイルへの変更は、もう一方のパスのハッシュ検証に反映されない可能性があります。

```
hardlink_a.py ─┐
               ├─ 同一 inode → 内容は同一
hardlink_b.py ─┘

Path.resolve():
  hardlink_a.py → /abs/path/hardlink_a.py  ← キャッシュキー A
  hardlink_b.py → /abs/path/hardlink_b.py  ← キャッシュキー B（別エントリ）

symlink.py → target.py:
  symlink.py → /abs/path/target.py         ← target.py と同一キー ✓
```

#### 推奨される代替手段

- **シンボリック リンク**: `resolve()` の実パスに解決され、ハッシュ検証との一貫性が保たれます。ただし、シンボリックリンクの参照先は**pack_subdir境界内**に限定されます。境界の外側を指すシンボリック リンクは実行時に拒否されます。
- **ファイル コピー**: 最も安全な方法です。各ファイルには独立したハッシュがあり、検証の問題はありません。

---

## API リファレンス

### rumi_syscall (外部通信)

コンテナ内から外部へのHTTP通信を行うためのモジュールです。 `import rumi_syscall`で使用。

|機能 |説明 |
|------|------|
| `http_request(method, url, headers=None, body=None, timeout_seconds=30.0)` |一般的な HTTP リクエスト |
| `get(url, headers=None, timeout_seconds=30.0)` |ショートカットを取得 |
| `post(url, body=None, headers=None, timeout_seconds=30.0)` | POST ショートカット |
| `post_json(url, data, headers=None, timeout_seconds=30.0)` | JSON POSTショートカット（Content-Type自動設定） |
| `put(url, body=None, headers=None, timeout_seconds=30.0)` |ショートカットを置く |
| `delete(url, headers=None, timeout_seconds=30.0)` |ショートカットを削除 |
| `patch(url, body=None, headers=None, timeout_seconds=30.0)` |パッチのショートカット |
| `head(url, headers=None, timeout_seconds=30.0)` |頭のショートカット |

戻り値は、`success` (bool)、`status_code` (int)、`headers` (dict)、`body` (str)、`error` (str)、`error_type` (str)、`latency_ms` (float)、`redirect_hops` (int)、`bytes_read` (int)、`final_url` を含む辞書です。 (文字列)など。

`request` は、`http_request` の別名です。 `rumi_syscall.request(...)` も同様の動作をします。

### rumi_capability (能力呼び出し)

コンテナ内から Capability を呼び出すためのモジュール。 `import rumi_capability`で使用。

|機能 |説明 |
|------|------|
| `call(permission_id, args=None, timeout_seconds=30.0, request_id=None)` |実行機能 |

戻り値は、`success` (bool)、`output` (Any)、`error` (str)、`error_type` (str)、`latency_ms` (float) を含む辞書です。

```python
import rumi_capability

result = rumi_capability.call("store.get", args={"store_id": "my_store", "key": "config"})
if result["success"]:
    data = result["output"]
```

---

## チュートリアル: 単純なパックを作成する

外部 API からデータを取得し、ストアに保存し、HTTP エンドポイント経由で返すパックを作成します。

### 1. ディレクトリ構造

```
ecosystem/weather_pack/
└── backend/
    ├── ecosystem.json
    ├── routes.json
    ├── blocks/
    │   ├── fetch_weather.py
    │   └── get_cached_weather.py
    └── flows/
        ├── fetch_weather.flow.yaml
        └── get_weather.flow.yaml
```

### 2. エコシステム.json

```json
{
  "pack_id": "weather_pack",
  "pack_identity": "github:author/weather_pack",
  "version": "1.0.0",
  "description": "天気情報を取得・キャッシュする Pack"
}
```

### 3. ブロック: fetch_weather.py

```python
import rumi_syscall
import rumi_capability

def run(input_data, context=None):
    city = input_data.get("city", "Tokyo")

    # 外部 API からデータ取得（Network Grant 必要）
    result = rumi_syscall.get(
        f"https://api.example.com/weather?city={city}",
        timeout_seconds=10.0
    )
    if not result["success"]:
        return {"error": result["error"]}

    import json
    weather = json.loads(result["body"])

    # Store に保存（store.set Grant 必要）
    rumi_capability.call("store.set", args={
        "store_id": "weather_cache",
        "key": f"weather/{city}",
        "value": weather
    })

    return {"weather": weather}
```

### 4. ブロック: get_cached_weather.py

```python
import rumi_capability

def run(input_data, context=None):
    city = input_data.get("city", "Tokyo")

    result = rumi_capability.call("store.get", args={
        "store_id": "weather_cache",
        "key": f"weather/{city}"
    })

    if result["success"] and result["output"].get("success"):
        return {"weather": result["output"]["value"]}
    return {"error": "No cached data"}
```

### 5. フローの定義

```yaml
# flows/fetch_weather.flow.yaml
flow_id: weather_pack.fetch
schedule:
  interval: 300
phases:
  - main
steps:
  - id: fetch
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: weather_pack
    file: blocks/fetch_weather.py
    input:
      city: "Tokyo"
    output: result
```

```yaml
# flows/get_weather.flow.yaml
flow_id: weather_pack.get
phases:
  - main
steps:
  - id: get_cached
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: weather_pack
    file: blocks/get_cached_weather.py
    input:
      city: "${ctx.city}"
    output: result
```

### 6. ルート.json

```json
{
  "routes": [
    {
      "method": "GET",
      "path": "/api/weather/{city}",
      "flow_id": "weather_pack.get",
      "description": "キャッシュ済みの天気情報を返す"
    }
  ]
}
```

### 7. 操作手順

```bash
# Pack を承認
curl -X POST http://localhost:8765/api/packs/weather_pack/approve \
  -H "Authorization: Bearer YOUR_TOKEN"

# Network Grant を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "weather_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'

# Store を作成
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "weather_cache", "root_path": "user_data/stores/weather_cache"}'

# Capability Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "weather_pack", "permission_id": "store.set", "config": {"allowed_store_ids": ["weather_cache"]}}'

curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "weather_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["weather_cache"]}}'

# 天気情報を取得
curl http://localhost:8765/api/weather/Tokyo \
  -H "Authorization: Bearer YOUR_TOKEN"
```
# Defaultspack 関数コントラクト

Defaultspack の機能は、Rumi の機能として利用できます。 HTTP ルートやdefaultspack ファイル パスに依存するのではなく、`defaults.ai.complete`、`defaultspack.chat.send`、または `defaultspack.ai.set_thinking_level` などのエイリアスを呼び出すことを優先します。例、権限、AI ツール ラッパーのガイダンスについては、[defaultspack-functions.md](defaultspack-functions.md) を参照してください。
