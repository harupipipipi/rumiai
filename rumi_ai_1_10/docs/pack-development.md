

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
8. [Capability の利用](#capability-の利用)
9. [lib（install / update）](#libinstall--update)
10. [pip 依存（requirements.lock）](#pip-依存requirementslock)
11. [permissions.json](#permissionsjson)
12. [Capability Handler の同梱](#capability-handler-の同梱)
13. [vocab / converter（上級）](#vocab--converter上級)
14. [Component（上級）](#component上級)
15. [注意事項](#注意事項)

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
  "description": "My first pack"
}
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `pack_id` | ✅ | Pack の識別子。ディレクトリ名と一致させる |
| `pack_identity` | ✅ | 配布元を示す識別子（例: `github:author/repo`）。Pack 更新時にこの値が変わると apply が拒否される |
| `version` | 任意 | セマンティックバージョニング |
| `description` | 任意 | 説明 |

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

JSON 互換の dict を返してください。戻り値は Flow の `output` フィールドで指定したコンテキストキーに格納されます。

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

## Capability の利用

Pack が capability handler（例: ファイルシステム読み取り、外部ツール実行等）を使用するには、該当する permission の Grant が Pack に付与されている必要があります。

Grant は Trust（handler のコードを信頼するか）とは独立しています。Trust が登録されていても Grant がなければ使用できません。

Grant の付与はユーザーまたは運用者が行います。詳細は [operations.md](operations.md) の「Capability Grant 管理」を参照してください。

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

このファイルはユーザーへの情報提供を目的とします。実際の権限付与は API 経由でユーザーが行います。

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

---

## 注意事項

- **InterfaceRegistry は内部 API です。** Pack から直接 IR を操作しないでください。
- **外部通信は必ず Egress Proxy 経由**で行ってください。`context["http_request"]` を使用します。
- **lib の書き込み先は `/data` のみです。** それ以外のパスへの書き込みは `--read-only` により失敗します。
- **pack_identity を変更しないでください。** 更新時に `pack_identity` が変わると apply が拒否されます。
- **principal_id は v1 では owner_pack に強制上書きされます。** Flow 定義で `principal_id` を指定しても無視されます。
```

