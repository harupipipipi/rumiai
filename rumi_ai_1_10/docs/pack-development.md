

> **クイックスタートガイド**: Pack 開発を始める方は [Pack 開発クイックスタートガイド](pack-development-guide.md) を参照してください。
```markdown
# Rumi AI OS — Pack Development Guide

Pack 開発者向けのガイドです。設計の全体像は [architecture.md](architecture.md)、運用手順は [operations.md](operations.md) を参照してください。

---

## 目次

1. [開発の流れ](#開発の流れ)
2. [最小構成](#最小構成)
3. [ecosystem.json](#ecosystemjson)
4. [ブロック（blocks）](#ブロックblocks)
5. [型ヒント・バリデーション](#型ヒントバリデーション)
6. [Flow 定義](#flow-定義)
7. [Flow → HTTP レスポンスマッピング](#flow--http-レスポンスマッピング)
8. [Flow Modifier](#flow-modifier)
9. [ネットワークアクセス](#ネットワークアクセス)
10. [context\["http\_request"\] 詳細仕様](#contexthttp_request-詳細仕様)
11. [Secrets の利用（Pack から）](#secrets-の利用pack-から)
12. [Capability の利用](#capability-の利用)
13. [Store API（Capability 経由）](#store-apicapability-経由)
14. [Pack 間連携パターン](#pack-間連携パターン)
15. [lib（install / update）](#libinstall--update)
16. [pip 依存（requirements.lock）](#pip-依存requirementslock)
17. [permissions.json](#permissionsjson)
18. [Capability Handler の同梱](#capability-handler-の同梱)
19. [vocab / converter（上級）](#vocab--converter上級)
20. [Component（上級）](#component上級)
21. [Pack 独自エンドポイント（routes.json）](#pack-独自エンドポイントroutesjson)
22. [HTTP ステータスコード制御](#http-ステータスコード制御)
23. [エラーハンドリング ベストプラクティス](#エラーハンドリング-ベストプラクティス)
24. [注意事項](#注意事項)
25. [API リファレンス](#api-リファレンス)
26. [チュートリアル: 簡単な Pack を作る](#チュートリアル-簡単な-pack-を作る)

---

## 開発の流れ

### Step 0: テンプレートで雛形を生成

```bash
python -m core_runtime.pack_scaffold my-pack --template minimal --output-dir ecosystem/
```

テンプレート種別:
- `minimal`: 最小構成（ecosystem.json + run.py）
- `capability`: Capability Handler 付き
- `flow`: Flow 定義付き
- `full`: 全部入り

1. **Pack を作る** — `ecosystem/<pack_id>/backend/` にファイルを配置
2. **ecosystem.json を書く** — Pack のメタデータ（`pack_id`, `pack_identity` 必須）
3. **blocks/ を書く** — `python_file_call` で呼ばれるコード
4. **Flow を書く** — `user_data/shared/flows/` または Pack 内 `flows/` に配置し、blocks を結線
5. **承認を得る** — ユーザーが Pack を承認
6. **実行** — 承認後、Flow 実行時に blocks が呼ばれる

---

## 最小構成

```
ecosystem/my_pack/
└── backend/
    ├── ecosystem.json
    └── blocks/
        └── hello.py
```

> **パスについて**: `ecosystem/<pack_id>/` が推奨パスです。`ecosystem/packs/<pack_id>/` も互換パスとしてサポートされますが、同一 `pack_id` が両方に存在する場合、`ecosystem/<pack_id>/` が優先されます。

---

## ecosystem.json

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "version": "1.0.0",
  "description": "My first pack",
  "pack_identity_vocabulary": ["my_pack"]
}
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `pack_id` | ✅ | Pack の識別子。ディレクトリ名と一致させる |
| `pack_identity` | ✅ | 配布元を示す識別子（例: `github:author/repo`）。Pack 更新時にこの値が変わると apply が拒否される |
| `version` | 任意 | セマンティックバージョニング |
| `description` | 任意 | 説明 |
| `pack_identity_vocabulary` | 任意 | Pack が使用する語彙のリスト。vocab.txt との連携に使用 |

### connectivity（Pack 間依存宣言）

`ecosystem.json` に `connectivity` フィールドを追加することで、Pack 間の依存関係を宣言できます。

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

| フィールド | 説明 |
|-----------|------|
| `provides` | この Pack が提供するサービス名のリスト |
| `requires` | この Pack が必要とするサービス名のリスト |

connectivity の `requires` / `provides` は、起動時の Pack ロード順序（load_order）の自動解決に使用されます。`requires` で指定したサービスを `provides` する Pack が先にロードされます。

手動指定（`ecosystem.json` の `load_order` フィールド）が存在する場合はそちらが優先されます。手動指定がない場合にのみ自動解決が適用されます。

現時点では connectivity のランタイムでの効果は load_order 自動解決のみです。将来的に拡張される可能性があります。

#### connectivity パターン例

| provides | 意味 | 典型的な Pack |
|----------|------|--------------|
| `ai.client` | AI API クライアント | OpenAI / Anthropic クライアント |
| `tool.registry` | ツール登録 | ツールマネージャー |
| `memory.store` | 記憶ストア | メモリ管理 |
| `ui.chat` | チャット UI | フロントエンド |

provides / requires の値はドット区切りの自由文字列です。OS は値の意味を解釈せず、load_order の自動解決にのみ使用します。Pack 開発者間で名前を合わせてください。

---

## ブロック（blocks）

`python_file_call` で呼ばれる Python ファイルです。

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

`run` 関数は `input_data` のみの 1 引数版も許可されます。

### 戻り値

JSON 互換の dict を返してください。戻り値は Flow の `output` フィールドで指定したコンテキストキーにそのまま格納されます。Kernel 内部のラッパー（`_kernel_step_status` 等）は自動的に除去され、ブロックが返した値がそのまま `ctx[output_key]` に入ります。

### 出力キー命名規則

Flow ステップの `output` に格納される値のキー名について以下の規則があります。

`_` プレフィックスで始まるキーは Kernel 内部キーとして予約されています。`python_file_call` の `run()` が返す dict に `_` プレフィックスのキー（例: `_kernel_step_status`、`_debug`）が含まれていた場合、Flow の `output` コンテキストに格納される際に自動除外されます。

Pack のブロックが返す出力キーには `_` プレフィックスを使用しないでください。意図せず除外される原因になります。

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

## 型ヒント・バリデーション

### run() 関数のシグネチャ

`python_file_call` で呼び出される `run()` 関数は、以下の3パターンのいずれかを受け付けます。実行エンジンが `inspect.signature` で引数の数を自動検出します。

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

### input_data の型保証

`input_data` は Flow 定義の `input` フィールドを JSON シリアライズ/デシリアライズした値です。したがって、含まれる型は JSON 由来の以下の型に限定されます。

| JSON 型 | Python 型 |
|---------|----------|
| object | `dict` |
| array | `list` |
| string | `str` |
| number（整数） | `int` |
| number（小数） | `float` |
| boolean | `bool` |
| null | `None` |

`input_data` 自体は通常 `dict` ですが、Flow 定義で直接スカラー値やリストを指定した場合はその型になります。

### context の型

`context` は `dict[str, Any]` です。主なキーは以下の通りです。

| キー | 型 | 説明 |
|------|----|------|
| `flow_id` | `str` | 実行中の Flow ID |
| `step_id` | `str` | 実行中のステップ ID |
| `phase` | `str` | 実行フェーズ名 |
| `ts` | `str` | 実行開始タイムスタンプ（ISO 8601 UTC） |
| `owner_pack` | `str \| None` | 所有 Pack ID |
| `inputs` | `dict` | input_data と同一 |
| `http_request` | `Callable` | HTTP リクエスト関数（[context\["http\_request"\] 詳細仕様](#contexthttp_request-詳細仕様) 参照） |
| `network_check` | `Callable` | ネットワークアクセスチェック関数 |
| `capability_socket` | `str \| None` | Capability UDS ソケットパス |

### 戻り値の型

`run()` の戻り値は JSON シリアライズ可能な値（`dict`、`list`、`str`、`int`、`float`、`bool`、`None`）であることが必要です。`None` を返した場合、Flow の output は `null` として扱われます。戻り値が `dict` の場合、その内容が Flow の `output` 変数に格納されます。

### バリデーションのベストプラクティス

`input_data` の内容は外部（Flow 定義やユーザー入力）由来であるため、必ずバリデーションを行ってください。

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

- 例外を投げるのではなく、`{"error": "..."}` を返して正常終了させる
- 必須フィールドは関数の先頭でまとめてチェックする
- `isinstance()` で型を厳密に確認する
- 数値の範囲やリストの長さにも上限を設ける

---

## Flow 定義

### 配置パス

| パス | 用途 |
|------|------|
| `user_data/shared/flows/` | 共有 Flow。複数 Pack をまたぐ結線に適しています |
| `ecosystem/<pack_id>/backend/flows/` | Pack 固有の Flow |

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

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `id` | ✅ | ステップ ID（Flow 内で一意） |
| `phase` | ✅ | 所属フェーズ |
| `priority` | 任意 | 実行優先度（昇順。デフォルト 100） |
| `type` | ✅ | `python_file_call` |
| `owner_pack` | 任意 | 所有 Pack（パスから推測される場合は省略可） |
| `file` | ✅ | 実行ファイルの相対パス |
| `input` | 任意 | 入力データ（変数展開可能） |
| `output` | 任意 | 出力先コンテキストキー |
| `timeout_seconds` | 任意 | タイムアウト秒数（デフォルト 60） |

#### handler

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

`handler` タイプは `input.handler` で指定された Kernel ハンドラー（`kernel:*`）または InterfaceRegistry 登録済みハンドラーを直接呼び出します。`input.args` がハンドラーの引数として渡されます。

#### set

```yaml
- id: set_default
  phase: prepare
  priority: 5
  type: set
  input:
    key: "model"
    value: "gpt-4"
```

> **注意**: `set` タイプは InterfaceRegistry に登録された `flow.construct.set` ハンドラーによって処理されます。Flow ローダーは `set` を標準ステップタイプとして解釈しますが、実行は construct 経由です。`set` construct が登録されていない場合、ステップはスキップされます。

#### flow（サブ Flow 呼び出し）

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

`flow` タイプは別の Flow をサブ Flow として呼び出します。再帰的な呼び出し（循環参照）は自動検出され、エラーになります。サブ Flow のコンテキストは親からディープコピーされ、`args` で指定した値が追加されます。

### 変数展開

`${ctx.key}` でコンテキスト内の値を参照できます。ネスト参照（`${ctx.user.id}`）も可能です。参照先が存在しない場合は `null` になります。

### スケジュール実行

Flow に `schedule` フィールドを追加することで、定期実行が可能です。

#### cron 式（5 フィールド: 分 時 日 月 曜日）

```yaml
flow_id: daily_cleanup
schedule:
  cron: "0 0 * * *"

phases:
  - main
steps:
  # ...
```

#### interval（秒指定、最小 10 秒）

```yaml
flow_id: health_check
schedule:
  interval: 30

phases:
  - main
steps:
  # ...
```

cron 式は `*`、`*/N`、数値、カンマ区切り、範囲（`N-M`）、範囲+ステップ（`N-M/S`）をサポートします。スケジューラーは 10 秒間隔の tick で評価されるため、cron の精度は分単位です。同一 Flow の重複実行は自動的に防止されます。

### Flow 制御プロトコル

ブロックの返り値で `__flow_control` キーを返すことで、Flow の実行を制御できます。

#### フロー中断

```python
def run(input_data, context=None):
    if not input_data.get("valid"):
        return {"__flow_control": "abort", "reason": "Invalid input"}
    return {"result": "ok"}
```

`{"__flow_control": "abort", "reason": "..."}` を返すと、以降のステップは実行されずにフローが中断されます。中断理由は diagnostics に記録されます。

> 現時点で `__flow_control` がサポートする値は `"abort"` のみです。その他の値は無視されます。

---

## Flow → HTTP レスポンスマッピング

Pack の `routes.json` で定義したエンドポイントが HTTP リクエストを受けると、Pack API Server（`pack_api_server.py`）は対応する Flow を実行し、その結果を HTTP レスポンスに変換して返却します。

### レスポンス変換の仕組み

現在の実装では、Flow の実行結果（`outputs`）は **常に JSON 形式で返却** されます。レスポンスは `APIResponse` データクラスを経由して生成されます。

```python
@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
```

Flow の実行が成功した場合:

```json
{
  "success": true,
  "data": { "...Flow outputs がここに入る..." },
  "error": null
}
```

Flow の実行が失敗した場合:

```json
{
  "success": false,
  "data": null,
  "error": "エラーメッセージ"
}
```

### ステータスコード

Pack API Server の `_send_response` は以下の HTTP ステータスコードを使用します。

| 状況 | ステータスコード |
|------|-----------------|
| Flow 実行成功 | `200 OK` |
| 認証失敗 | `401 Unauthorized` |
| 入力不正 | `400 Bad Request` |
| ルート未発見 | `404 Not Found` |
| 内部エラー | `500 Internal Server Error` |

### ヘッダー

レスポンスには以下のヘッダーが自動付与されます。

| ヘッダー | 値 | 条件 |
|---------|-----|------|
| `Content-Type` | `application/json; charset=utf-8` | 常に付与 |
| `Access-Control-Allow-Origin` | リクエスト元 Origin | CORS 許可リストに一致する場合 |
| `Vary` | `Origin` | CORS ヘッダー付与時 |

### 特殊キーによる制御

現時点では `_status_code`、`_headers`、`_body` 等の特殊キーによる HTTP レスポンスの直接制御は **サポートされていません**。Flow の outputs は常に `APIResponse` の `data` フィールドに格納され、`application/json` 形式で返却されます。

カスタムステータスコードやヘッダーの制御が必要な場合は、[HTTP ステータスコード制御](#http-ステータスコード制御) を参照してください。

---

## Flow Modifier

既存 Flow に後から機能を差し込む仕組みです。

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

### 使用可能なアクション

| action | 説明 |
|--------|------|
| `inject_before` | 指定ステップの前に挿入 |
| `inject_after` | 指定ステップの後に挿入 |
| `append` | フェーズの末尾に追加 |
| `replace` | 指定ステップを置換 |
| `remove` | 指定ステップを削除 |

> **phase の制約**: Modifier の `phase` は対象 Flow の `phases` リストに含まれている必要があります。存在しない phase を指定した場合、Modifier はスキップされます。

> **適用順序**: Modifier は phase → priority → modifier_id の順でソートされ、決定的に適用されます。同一注入点（同じ `target_step_id` への `inject_before` / `inject_after`）に複数の Modifier がある場合は priority → step.id → modifier_id の順で一括挿入され、インデックスずれによる非決定性を防ぎます。`replace` / `remove` は inject / append より先に適用されます。

### ワイルドカード target_flow_id

`target_flow_id` にワイルドカードパターンを使用して、複数の Flow に同時に Modifier を適用できます。

| パターン | 意味 |
|----------|------|
| `*` | 全ての Flow に適用 |
| `my_pack.*` | `my_pack.` で始まる全ての Flow に適用 |

マッチングには Python の `fnmatch` が使用されます。

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

### requires 条件

```yaml
requires:
  interfaces:
    - "ai.client"
  capabilities:
    - "tool_support"
```

条件が満たされない場合、Modifier はスキップされます。

---

## ネットワークアクセス

### 概要

Pack は Docker `--network=none` で隔離されるため、直接外部通信できません。外部通信には Network Grant の付与が必要で、全てのリクエストは Egress Proxy（UDS ソケット）を経由します。

### ブロック内での HTTP リクエスト

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

> **タイムアウト上限**: `timeout_seconds` の最大値は 120 秒です。120 を超える値を指定しても 120 秒に切り詰められます。この上限は `rumi_syscall` と `rumi_capability` の両方に適用されます。

### アクセス可否の事前チェック

```python
def run(input_data, context=None):
    check = context.get("network_check")
    result = check("api.openai.com", 443)

    if not result["allowed"]:
        return {"error": result["reason"]}

    # 通信可能
```

### Grant の取得方法

ユーザーまたは運用者が API で付与します。詳細は [operations.md](operations.md) の「ネットワーク権限管理」を参照してください。

---

## context["http_request"] 詳細仕様

`python_file_call` の `run(input_data, context)` で渡される `context["http_request"]` は、Pack コードが外部 HTTP 通信を行うための唯一の手段です。

### 関数シグネチャ

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

| パラメータ | 型 | デフォルト | 説明 |
|------------|-----|-----------|------|
| `method` | `str` | （必須） | HTTP メソッド。`GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD` |
| `url` | `str` | （必須） | リクエスト先の完全な URL |
| `headers` | `dict[str, str] \| None` | `None` | HTTP リクエストヘッダー |
| `body` | `str \| None` | `None` | リクエストボディ（文字列）。JSON を送る場合は `json.dumps()` した文字列を渡す |
| `timeout_seconds` | `float` | `30.0` | タイムアウト秒数。最大 `120.0` 秒に制限される |

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

### error_type 一覧

| error_type | 説明 |
|------------|------|
| `socket_not_found` | Egress Proxy ソケットが見つからない |
| `permission_denied` | ソケットへのアクセス権限がない |
| `connection_refused` | Egress Proxy への接続が拒否された |
| `timeout` | リクエストがタイムアウトした |
| `syscall_error` | プロトコルレベルのエラー |
| `json_decode_error` | レスポンスの JSON パースに失敗 |
| `grant_denied` | Network Grant によりアクセスが拒否された |

### UDS Egress Proxy 経由の通信

Pack コードからの全ての外部 HTTP 通信は **UDS（Unix Domain Socket）Egress Proxy** を経由します。Pack コードが直接ネットワーク通信を行うことはできません。

通信フロー:

```
Pack コード (run関数)
  → context["http_request"]()
    → UDS ソケット (/run/rumi/egress/packs/{pack_id}.sock)
      → Egress Proxy (Kernel 側)
        → Network Grant Manager でアクセス許可を検証
          → 許可されていれば外部 HTTP リクエストを実行
          → 拒否されていれば grant_denied エラーを返却
```

> ソケットパスは `RUMI_EGRESS_SOCK_DIR` 環境変数で変更可能です。デフォルトは `/run/rumi/egress/packs` です。

### コンテナモードとホストモードの違い

| 項目 | コンテナモード（strict） | ホストモード（permissive） |
|------|--------------------------|---------------------------|
| ネットワーク | `--network=none`（完全隔離） | ホストのネットワークを使用 |
| 通信経路 | UDS ソケット経由のみ | UDS ソケット経由（ヘルパー関数経由） |
| ソケットパス | `/run/rumi/egress/packs/{pack_id}.sock`（コンテナ内マウント） | `{RUMI_EGRESS_SOCK_DIR}/{pack_id}.sock` |
| Grant 検証 | Egress Proxy が検証 | Egress Proxy が検証 |
| セキュリティ | Docker 隔離 + UDS 制限 | 警告付きで実行（本番非推奨） |

コンテナモード（`RUMI_SECURITY_MODE=strict`）では、Docker コンテナは `--network=none` で起動されるため、UDS ソケット以外の通信手段はありません。ホストモード（`RUMI_SECURITY_MODE=permissive`）では Docker なしで実行されますが、`context["http_request"]` は同様に Egress Proxy を経由するため、Network Grant による制御は有効です。

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

## Secrets の利用（Pack から）

Pack がシークレット（API キー等）を取得するには、`secrets.get` Capability を使用します。運用者が Secrets の登録と Grant の付与を行った後に利用可能になります。

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

`secrets.get` の Grant には `grant_config.allowed_keys` でアクセス可能なキーを明示的に指定する必要があります。`allowed_keys` が空または未指定の場合、全てのキーへのアクセスが拒否されます（fail-closed）。

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

- `get` は Capability 経由のみで取得可能です。シークレットの値を直接再表示する API は存在しません
- `secrets.get` には rate limit が適用されます（デフォルト 60 回/分/Pack、環境変数 `RUMI_SECRET_GET_RATE_LIMIT` で変更可能、sliding window 方式）
- 値はログ・監査・例外メッセージに一切含まれません
- キーの存在有無もエラーメッセージからは判別できません（"Access denied or secret not found" で統一）

---

## Capability の利用

Pack が capability handler（例: ファイルシステム読み取り、外部ツール実行等）を使用するには、該当する permission の Grant が Pack に付与されている必要があります。

### Trust と Grant の関係

Capability の利用には 2 段階の承認が必要です。

1. **Trust 登録**（handler 承認）: handler のコード（sha256）を信頼済みとして登録
2. **Grant 付与**（権限付与）: 承認済み handler の permission を Pack に付与

```
handler.py が信頼される（Trust 登録）
    ↓
Pack に permission が付与される（Grant 付与）
    ↓
Pack が capability を使用可能
```

Trust が登録されていても Grant がなければ使用できません。逆に、Grant があっても Trust が登録されていない handler は実行できません。

### Capability の呼び出し方

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})
if result["success"]:
    content = result["output"]
else:
    error = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
```

### Built-in Capability Handler

以下の Capability Handler はコアランタイムに同梱されており、Trust 登録なしで利用可能です（Grant は別途必要）。

| permission_id | handler_id | 説明 | risk |
|---------------|-----------|------|------|
| `secrets.get` | `builtin.secrets.get` | シークレット値の読み取り | high |
| `store.get` | `builtin.store.get` | Store からの値の読み取り | low |
| `store.set` | `builtin.store.set` | Store への値の書き込み | medium |
| `store.delete` | `builtin.store.delete` | Store からの値の削除 | medium |
| `store.list` | `builtin.store.list` | Store 内のキー一覧取得 | low |
| `pack.inbox.send` | `builtin.pack.inbox.send` | 他 Pack コンポーネントの inbox へ JSON パッチ/置換を送信 | medium |
| `pack.update.propose_patch` | `builtin.pack.update.propose_patch` | 他 Pack へのファイル変更を提案（ステージング作成、自動適用なし） | high |

### Grant の付与

Grant の付与はユーザーまたは運用者が API で行います。詳細は [operations.md](operations.md) の「Capability Grant 管理」を参照してください。

```bash
# 例: store.get の Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["my_store"]}}'
```

### Grant の設定（grant_config）

Grant には `config` で制限を設定できます。設定内容は permission ごとに異なります。

| permission_id | grant_config キー | 説明 |
|---------------|-------------------|------|
| `secrets.get` | `allowed_keys` | アクセス可能なキー名のリスト（必須、空なら全拒否） |
| `store.get/set/delete/list` | `allowed_store_ids` | アクセス可能な store_id のリスト（必須、空なら全拒否） |
| `store.set` | `max_value_bytes` | 書き込み最大サイズ（バイト、デフォルト 1MB） |

`allowed_keys` / `allowed_store_ids` は fail-closed です。空リストまたは未指定の場合、全てのアクセスが拒否されます。

### エラーハンドリング

Capability 呼び出しが失敗した場合、`success: False` を含む dict が返されます。

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

| error_type | 説明 |
|------------|------|
| `grant_denied` | Pack に permission の Grant が付与されていない |
| `trust_denied` | handler の sha256 が Trust Store に登録されていない |
| `handler_not_found` | 指定された permission_id に対応する handler が存在しない |
| `execution_error` | handler の実行中にエラーが発生 |
| `timeout` | 実行がタイムアウトした |
| `socket_not_found` | Capability ソケットが見つからない |

---

## Store API（Capability 経由）

### 概要

Store は Pack 間で共有可能なキーバリューストアです。Store の操作は Capability 経由で行います。運用者が Capability の Grant を Pack に付与することでアクセスが有効になります。

### 利用可能な permission_id

| permission_id | 説明 | args |
|---------------|------|------|
| `store.get` | Store から値を読み取り | `store_id`, `key` |
| `store.set` | Store に値を書き込み | `store_id`, `key`, `value` |
| `store.delete` | Store から値を削除 | `store_id`, `key` |
| `store.list` | Store 内のキー一覧を取得 | `store_id`, `prefix`（任意） |

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

> `store.list` の `output` には `success`（bool）と `keys`（キー名の配列）が含まれます。

```python
# 値の削除
result = rumi_capability.call("store.delete", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
```

### Grant 設定

`store.*` の Grant には `grant_config` で制限を設定できます:

| grant_config キー | 説明 | デフォルト |
|-------------------|------|-----------|
| `allowed_store_ids` | アクセスを許可する store_id のリスト | `[]`（空リストの場合、全 Store へのアクセスが拒否される。アクセスするには明示的に store_id を指定する必要がある） |
| `max_value_bytes` | `store.set` の最大値サイズ（バイト） | 1MB（1048576） |

`allowed_store_ids` は fail-closed です。Grant 作成時に `allowed_store_ids` を指定しない、または空リスト `[]` を指定した場合、その Grant では全ての Store へのアクセスが拒否されます。Pack が Store にアクセスするには、運用者が明示的に store_id をリストに追加する必要があります。

### Store の作成

Store の作成は運用 API で行います:

```bash
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "my_store", "root_path": "user_data/stores/my_store"}'
```

> **store_id の制約**: `store_id` は `^[a-zA-Z0-9_-]{1,64}$` に一致する必要があります。

### Built-in Capability Handler 一覧

以下の Capability Handler はコアランタイムに同梱されており、Trust 登録なしで利用可能です（Grant は別途必要）。

| permission_id | handler_id | 説明 | risk |
|---------------|-----------|------|------|
| `secrets.get` | `builtin.secrets.get` | シークレット値の読み取り | high |
| `store.get` | `builtin.store.get` | Store からの値の読み取り | low |
| `store.set` | `builtin.store.set` | Store への値の書き込み | medium |
| `store.delete` | `builtin.store.delete` | Store からの値の削除 | medium |
| `store.list` | `builtin.store.list` | Store 内のキー一覧取得 | low |
| `pack.inbox.send` | `builtin.pack.inbox.send` | 他 Pack コンポーネントの inbox へ JSON パッチ/置換を送信 | medium |
| `pack.update.propose_patch` | `builtin.pack.update.propose_patch` | 他 Pack へのファイル変更を提案（ステージング作成、自動適用なし） | high |

---

## Pack 間連携パターン

### 共有 Flow での結線

複数の Pack のブロックを `user_data/shared/flows/` に配置した Flow で結線できます。各 Pack は互いを知る必要がありません。

```yaml
# user_data/shared/flows/ai_pipeline.flow.yaml
flow_id: ai_pipeline
phases:
  - prepare
  - generate
  - postprocess

steps:
  - id: load_tools
    phase: prepare
    priority: 50
    type: python_file_call
    owner_pack: tool_pack
    file: blocks/load_tools.py
    output: tools

  - id: generate
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      tools: "${ctx.tools}"
    output: response
```

### Store 経由のデータ受け渡し

異なる Flow で動作する Pack 間でデータを共有するには、Store を使用します。

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

## lib（install / update）

### 概要

Pack の初期化・更新時に一度だけ実行されるスクリプトです。普段は実行されません。

### ファイル構成

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

### context で提供される情報

| キー | 説明 |
|------|------|
| `pack_id` | Pack ID |
| `lib_type` | `"install"` または `"update"` |
| `ts` | タイムスタンプ |
| `lib_dir` | lib ディレクトリパス（コンテナ内: `/lib`） |
| `data_dir` | 書き込み可能ディレクトリ（コンテナ内: `/data`、ホスト: `user_data/packs/{pack_id}/`） |

### セキュリティ制約

strict モードでは Docker コンテナ内で隔離実行されます。`--network=none`、`--read-only`。書き込みは `/data`（= `user_data/packs/{pack_id}/`）のみ可能です。

---

## pip 依存（requirements.lock）

### 概要

Pack が PyPI パッケージに依存する場合、`requirements.lock` を同梱します。

### 配置パス

以下の順に探索されます:

1. `<pack_subdir>/requirements.lock`
2. `<pack_subdir>/backend/requirements.lock`（互換）

### フォーマット

`NAME==VERSION` 行のみ許可です。コメント行と空行は可。

```
requests==2.31.0
flask==3.0.0
```

以下は禁止されます: `-e`、`git+`、`http://`、`https://`、`file:`、`../`、`/`、`--` オプション行、`@` direct reference。

### Pack コードからの利用

承認・インストール後は通常通り `import` するだけです。

```python
import requests  # pip で導入された依存

def run(input_data, context=None):
    resp = requests.get("https://api.example.com/data")
    return {"data": resp.json()}
```

実行コンテナでは site-packages が `/pip-packages:ro` としてマウントされ、`PYTHONPATH` に追加されます。

### 承認の取得方法

ユーザーまたは運用者が API で承認します。詳細は [operations.md](operations.md) の「pip 依存ライブラリ管理」を参照してください。

---

## permissions.json

Pack が必要とする権限を宣言するファイルです。

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

permissions.json は宣言的であり、ランタイムで強制されません。実際のアクセス制御は Capability Grant と Network Grant で行われます。このファイルはユーザーへの情報提供（この Pack がどのような権限を必要とするか）を目的としています。

---

## Capability Handler の同梱

Pack が capability handler を提供する場合、以下の規約に従います。

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

Pack の `pack_subdir`（通常 `ecosystem/<pack_id>/backend/`）配下の `share/capability_handlers/<slug>/` に配置します。

### handler.json

```json
{
  "handler_id": "fs_read_handler",
  "permission_id": "fs.read",
  "entrypoint": "handler.py:execute",
  "description": "ファイルシステム読み取り handler",
  "risk": "ファイルシステムへの読み取りアクセスを提供"
}
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `handler_id` | ✅ | ハンドラーの一意識別子 |
| `permission_id` | ✅ | 要求される権限 ID |
| `entrypoint` | ✅ | 実行エントリポイント（例: `handler.py:execute`） |
| `description` | 任意 | 説明 |
| `risk` | 任意 | リスクの説明 |

候補は scan で検出され、ユーザーの approve を経て `user_data/capabilities/handlers/<slug>/` にコピーされます。approve は Trust（sha256 allowlist）のみを登録し、Grant は別途必要です。

---

## vocab / converter（上級）

> 通常の Pack 開発では使用する必要はありません。互換性吸収のための高度な機能です。

### vocab.txt

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

同じ行に書かれた語は同義として扱われます。

### converters

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

---

## Component（上級）

Component は `components/{component_id}/manifest.json` を持つ単位で、ライフサイクル管理（setup 等）に使用されます。`python_file_call` は components を特別扱いしないため、`file` フィールドに相対パスを明示してください。

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

### setup.py の基本パターン

Component の初期化処理は `components/{component_id}/setup.py` に記述します。

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

setup は起動時の `kernel:component.load` ステップで実行されます。

---

## Pack 独自エンドポイント（routes.json）

### 概要

Pack は `routes.json` を同梱することで、HTTP API サーバーに独自のエンドポイントを登録できます。受信したリクエストは指定された Flow を実行し、その結果をレスポンスとして返します。

### 配置パス

`ecosystem/<pack_id>/backend/routes.json`

### routes.json の形式

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

`{param}` 記法でパスパラメータを定義できます。パスパラメータの値は Flow の `inputs` に自動的に含まれます。

例: `/api/orgs/{org_id}/tasks/{task_id}` にリクエストした場合、`inputs.org_id` と `inputs.task_id` にそれぞれの値が入ります。

### GET クエリパラメータ

GET リクエストのクエリパラメータも `inputs` に含まれます。

### Raw Body / Headers の取得

Flow の `inputs` には以下の特殊キーも含まれます:

| キー | 説明 |
|------|------|
| `_raw_body` | リクエストボディの base64 エンコード値 |
| `_headers` | リクエストヘッダーの dict |
| `_method` | HTTP メソッド（GET, POST 等） |
| `_path` | リクエストパス |

### ルートの再読み込み

```bash
curl -X POST http://localhost:8765/api/routes/reload \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 登録済みルートの確認

```bash
curl http://localhost:8765/api/routes \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## HTTP ステータスコード制御

### 現在の仕様

現在の Pack API Server の実装では、Pack の `routes.json` エンドポイントから返却される HTTP ステータスコードを Pack 側から **直接制御することはできません**。

Flow の outputs に `_status_code` 等の特殊キーを含めても、それはレスポンスの `data` フィールドにそのまま含まれるだけで、HTTP ステータスコードには反映されません。

### ステータスコードの決定ロジック

Pack API Server は以下のロジックでステータスコードを決定します。

| 判定順 | 状況 | ステータスコード |
|--------|------|-----------------|
| 1 | 認証失敗 | `401` |
| 2 | 入力バリデーション失敗 | `400` |
| 3 | ルート未発見 | `404` |
| 4 | Flow 実行成功 | `200`（固定） |
| 5 | Flow 実行でエラー dict 返却 | `200`（data にエラーが含まれるが HTTP は 200） |
| 6 | Flow 実行で例外発生 | `500` |

つまり、Flow が正常に完了して `{"error": "not found"}` を返した場合でも、HTTP ステータスコードは `200 OK` になります。

### 推奨パターン

現在の制約のもとでは、エラーをクライアントに伝える場合はレスポンスボディ内の `success` フィールドと `error` フィールドを使用してください。

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

クライアント側では `data.error` の有無で成功/失敗を判定します。

### 将来対応予定

将来のバージョンで、Flow outputs 内の特殊キー（`_status_code`、`_headers` 等）を認識して HTTP レスポンスに反映する機能の追加が検討されています。

---

## エラーハンドリング ベストプラクティス

### python_file_call の run() で例外が発生した場合

`run()` 関数内で捕捉されない例外が発生すると、実行エンジンは以下の処理を行います。

**コンテナモード**: Docker プロセスが非ゼロの終了コードで終了し、stderr の内容がエラーメッセージとして記録されます。`ExecutionResult` の `success` は `False`、`error_type` は `"container_execution_error"` になります。

**ホストモード（permissive）**: 例外が `ThreadPoolExecutor` の `Future` から伝播し、同様に `ExecutionResult` の `success` が `False` になります。

いずれの場合も、Kernel のハンドラ（`_h_python_file_call`）は `_kernel_step_status: "failed"` を返します。

### 推奨: try-except で包んで error dict を return する

例外を外に漏らすと、スタックトレースがログに記録されるだけで呼び出し元の Flow に有用な情報が渡りません。必ず try-except で包み、構造化されたエラー情報を返してください。

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

### Flow の step 失敗時の動作

Flow 内のステップが失敗した場合の動作は、Flow 定義の `defaults` とステップごとの `on_error` 設定によって決まります。

| 設定 | 動作 |
|------|------|
| `defaults.fail_soft: true`（デフォルト） | ステップ失敗を記録して次のステップへ進む |
| `defaults.fail_soft: false` | ステップ失敗時に Flow 全体を中断する |
| `on_error.action: "abort"` | このステップの失敗時に Flow を中断する |
| `on_error.action: "continue"` | このステップの失敗時でも次へ進む |
| `on_error.action: "disable_target"` | 対象を無効化して次へ進む |

Flow レベルのエラーハンドラが InterfaceRegistry に `flow.error_handler` として登録されている場合、ステップ例外発生時にそのハンドラが呼び出されます。エラーハンドラは `"abort"`（中断）、`"retry"`（再試行）、またはそれ以外（継続）を返すことで動作を制御できます。

### capability.call() 失敗時の戻り値の扱い方

`rumi_capability` モジュール経由で Capability を呼び出した場合、失敗時は `success: False` を含む dict が返されます。

```python
import rumi_capability

result = rumi_capability.call(
    capability_id="store_get",
    input_data={"store_id": "my_store", "key": "my_key"},
)

if not result.get("success", False):
    # エラー処理
    error_msg = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
    return {"error": error_msg, "error_type": error_type}

# 成功時の処理
value = result.get("output", {}).get("value")
```

Capability 呼び出しの失敗原因には以下があります。

| error_type | 説明 |
|------------|------|
| `approval_denied` | Capability の使用が承認されていない |
| `grant_denied` | Capability Grant が付与されていない |
| `trust_denied` | Trust Store による検証に失敗した |
| `handler_not_found` | 指定された Capability Handler が存在しない |
| `execution_error` | Handler の実行中にエラーが発生した |
| `timeout` | 実行がタイムアウトした |
| `socket_not_found` | Capability ソケットが見つからない |

これらのエラーも try-except ではなく、戻り値の `success` フィールドで判定することを推奨します。

---

## 注意事項

- **InterfaceRegistry は内部 API です。** Pack から直接 IR を操作しないでください。
- **外部通信は必ず Egress Proxy 経由**で行ってください。`context["http_request"]` を使用します。
- **lib の書き込み先は `/data` のみです。** それ以外のパスへの書き込みは `--read-only` により失敗します。
- **pack_identity を変更しないでください。** 更新時に `pack_identity` が変わると apply が拒否されます。
- **principal_id は v1 では owner_pack に強制上書きされます。** Flow 定義や Modifier で `principal_id` を指定しても、実行時には `owner_pack` の値が principal として使用されます。不一致が検出された場合は監査ログに警告が記録されます。
- **レスポンスサイズ上限について**: Egress Proxy（`rumi_syscall`）および Capability クライアント（`rumi_capability`）のレスポンス上限は 4MB（`RUMI_MAX_RESPONSE_BYTES` で変更可能）です。ただし、Capability Executor（サーバー側サブプロセス実行）のレスポンス上限は 1MB です。
- **store.set の値サイズ上限はデフォルト 1MB です。** Grant の `grant_config.max_value_bytes` で変更可能です。
- **FlowScheduler の interval 最小値は 10 秒です。** 10 秒未満を指定しても 10 秒に切り上げられます。
- **同時 Flow 実行数はデフォルト 10 です。** `RUMI_MAX_CONCURRENT_FLOWS` 環境変数で変更可能です。
- **Capability 実行のタイムアウト上限は 120 秒です。** `rumi_capability.call()` の `timeout_seconds` に 120 を超える値を指定しても 120 秒に制限されます。デフォルトは 30 秒です。

### ハードリンクの非サポート

Pack ディレクトリ（`ecosystem/<pack_id>/`）内でのハードリンクの使用は **非サポート** です。

#### 理由

Pack 承認・ハッシュ検証システムは、ファイルパスを `Path.resolve()` で正規化した値をキャッシュキーとして使用します。シンボリックリンクは `resolve()` によって実体パスに解決されるため、リンク元とリンク先が同一キャッシュエントリに統合されます。一方、ハードリンクは `resolve()` で統合されません（各パスエントリが独立して保持される）。そのため、同一 inode を指す複数パスが別々のキャッシュエントリとして扱われ、一方のパス経由でファイルを変更しても他方のハッシュ検証に反映されない可能性があります。

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

#### 推奨代替

- **シンボリックリンク**: `resolve()` で実体パスに解決されるため、ハッシュ検証との整合性が保たれます。ただし、シンボリックリンクの参照先は **pack_subdir boundary 内** に限定されます。boundary 外を指すシンボリックリンクは実行時に拒否されます。
- **ファイルコピー**: 最も安全な方法です。各ファイルが独立したハッシュを持ち、検証に問題が生じません。

---

## API リファレンス

### rumi_syscall（外部通信）

コンテナ内から外部 HTTP 通信を行うためのモジュールです。`import rumi_syscall` で使用します。

| 関数 | 説明 |
|------|------|
| `http_request(method, url, headers=None, body=None, timeout_seconds=30.0)` | 汎用 HTTP リクエスト |
| `get(url, headers=None, timeout_seconds=30.0)` | GET ショートカット |
| `post(url, body=None, headers=None, timeout_seconds=30.0)` | POST ショートカット |
| `post_json(url, data, headers=None, timeout_seconds=30.0)` | JSON POST ショートカット（Content-Type 自動設定） |
| `put(url, body=None, headers=None, timeout_seconds=30.0)` | PUT ショートカット |
| `delete(url, headers=None, timeout_seconds=30.0)` | DELETE ショートカット |
| `patch(url, body=None, headers=None, timeout_seconds=30.0)` | PATCH ショートカット |
| `head(url, headers=None, timeout_seconds=30.0)` | HEAD ショートカット |

戻り値は dict で、`success`（bool）、`status_code`（int）、`headers`（dict）、`body`（str）、`error`（str）、`error_type`（str）、`latency_ms`（float）、`redirect_hops`（int）、`bytes_read`（int）、`final_url`（str）等を含みます。

`request` は `http_request` のエイリアスです。`rumi_syscall.request(...)` でも同じ動作になります。

### rumi_capability（Capability 呼び出し）

コンテナ内から Capability を呼び出すためのモジュールです。`import rumi_capability` で使用します。

| 関数 | 説明 |
|------|------|
| `call(permission_id, args=None, timeout_seconds=30.0, request_id=None)` | Capability を実行 |

戻り値は dict で、`success`（bool）、`output`（Any）、`error`（str）、`error_type`（str）、`latency_ms`（float）を含みます。

```python
import rumi_capability

result = rumi_capability.call("store.get", args={"store_id": "my_store", "key": "config"})
if result["success"]:
    data = result["output"]
```

---

## チュートリアル: 簡単な Pack を作る

外部 API からデータを取得し、Store に保存し、HTTP エンドポイントで返却する Pack を作ります。

### 1. ディレクトリ構成

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

### 2. ecosystem.json

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

### 5. Flow 定義

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

### 6. routes.json

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

### 7. 運用手順

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
```