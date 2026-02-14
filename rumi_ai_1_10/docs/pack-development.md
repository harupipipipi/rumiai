

```markdown
# Rumi AI OS — Pack Development Guide

Pack 開発者向けのガイドです。設計の全体像は [architecture.md](architecture.md)、運用手順は [operations.md](operations.md) を参照してください。

---

## 目次

1. [開発の流れ](#開発の流れ)
2. [最小構成](#最小構成)
3. [ecosystem.json](#ecosystemjson)
4. [ブロック（blocks）](#ブロックblocks)
5. [Flow 定義](#flow-定義)
6. [Flow Modifier](#flow-modifier)
7. [ネットワークアクセス](#ネットワークアクセス)
8. [Secrets の利用（Pack から）](#secrets-の利用pack-から)
9. [Capability の利用](#capability-の利用)
10. [Store API（Capability 経由）](#store-apicapability-経由)
11. [Pack 間連携パターン](#pack-間連携パターン)
12. [lib（install / update）](#libinstall--update)
13. [pip 依存（requirements.lock）](#pip-依存requirementslock)
14. [permissions.json](#permissionsjson)
15. [Capability Handler の同梱](#capability-handler-の同梱)
16. [vocab / converter（上級）](#vocab--converter上級)
17. [Component（上級）](#component上級)
18. [Pack 独自エンドポイント（routes.json）](#pack-独自エンドポイントroutesjson)
19. [注意事項](#注意事項)
20. [API リファレンス](#api-リファレンス)
21. [チュートリアル: 簡単な Pack を作る](#チュートリアル-簡単な-pack-を作る)

---

## 開発の流れ

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
            - http_request(method, url, ...) -> ProxyResponse

    Returns:
        JSON 互換の dict
    """
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

`run` 関数は `input_data` のみの 1 引数版も許可されます。

### 戻り値

JSON 互換の dict を返してください。戻り値は Flow の `output` フィールドで指定したコンテキストキーにそのまま格納されます。Kernel 内部のラッパー（`_kernel_step_status` 等）は自動的に除去され、ブロックが返した値がそのまま `ctx[output_key]` に入ります。

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

cron 式は `*`、`*/N`、数値、カンマ区切り、範囲（`N-M`）、範囲+ステップ（`N-M/S`）をサポートします。同一 Flow の重複実行は自動的に防止されます。

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
- `secrets.get` には rate limit が適用されます（デフォルト 60 回/分/Pack、`RUMI_SECRET_GET_RATE_LIMIT` で変更可能）
- 値はログ・監査・例外メッセージに一切含まれません
- キーの存在有無もエラーメッセージからは判別できません（"Access denied or secret not found" で統一）

---

## Capability の利用

Pack が capability handler（例: ファイルシステム読み取り、外部ツール実行等）を使用するには、該当する permission の Grant が Pack に付与されている必要があります。

Grant は Trust（handler のコードを信頼するか）とは独立しています。Trust が登録されていても Grant がなければ使用できません。

Grant の付与はユーザーまたは運用者が行います。詳細は [operations.md](operations.md) の「Capability Grant 管理」を参照してください。

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
    user = result["output"]["value"]

# キー一覧
result = rumi_capability.call("store.list", args={
    "store_id": "my_store",
    "prefix": "users/"
})

# 値の削除
result = rumi_capability.call("store.delete", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
```

### Grant 設定

`store.set` の Grant には `grant_config` で制限を設定できます:

| grant_config キー | 説明 | デフォルト |
|-------------------|------|-----------|
| `allowed_store_ids` | アクセスを許可する store_id のリスト | `[]`（制限なし） |
| `max_value_bytes` | `store.set` の最大値サイズ（バイト） | 1MB（1048576） |

### Store の作成

Store の作成は運用 API で行います:

```bash
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "my_store", "root_path": "user_data/stores/my_store"}'
```

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

## 注意事項

- **InterfaceRegistry は内部 API です。** Pack から直接 IR を操作しないでください。
- **外部通信は必ず Egress Proxy 経由**で行ってください。`context["http_request"]` を使用します。
- **lib の書き込み先は `/data` のみです。** それ以外のパスへの書き込みは `--read-only` により失敗します。
- **pack_identity を変更しないでください。** 更新時に `pack_identity` が変わると apply が拒否されます。
- **principal_id は v1 では owner_pack に強制上書きされます。** Flow 定義で `principal_id` を指定しても無視されます。
- **レスポンスサイズ上限は 4MB です。** Capability のレスポンスおよび Egress Proxy のレスポンスは最大 4MB（`RUMI_MAX_RESPONSE_BYTES` で変更可能）です。
- **store.set の値サイズ上限はデフォルト 1MB です。** Grant の `grant_config.max_value_bytes` で変更可能です。
- **FlowScheduler の interval 最小値は 10 秒です。** 10 秒未満を指定しても 10 秒に切り上げられます。
- **同時 Flow 実行数はデフォルト 10 です。** `RUMI_MAX_CONCURRENT_FLOWS` 環境変数で変更可能です。

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

戻り値は dict で、`success`（bool）、`status_code`（int）、`headers`（dict）、`body`（str）、`error`（str）等を含みます。

### rumi_capability（Capability 呼び出し）

コンテナ内から Capability を呼び出すためのモジュールです。`import rumi_capability` で使用します。

| 関数 | 説明 |
|------|------|
| `call(permission_id, args=None, timeout_seconds=30.0, request_id=None)` | Capability を実行 |

戻り値は dict で、`success`（bool）、`output`（Any）、`error`（str）、`latency_ms`（float）を含みます。

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