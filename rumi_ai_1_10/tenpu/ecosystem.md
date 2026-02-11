

```markdown
# Rumi AI Ecosystem 開発ガイド

Pack/Component開発者向けの包括的なドキュメントです。

---

## 目次

1. [設計思想](#設計思想)
2. [アーキテクチャ概要](#アーキテクチャ概要)
3. [ディレクトリ構造](#ディレクトリ構造)
4. [Flow システム](#flowシステム)
5. [python_file_call（ブロック実行）](#python_file_callブロック実行)
6. [Flow Modifier（差し込み）](#flow-modifier差し込み)
7. [権限モデル](#権限モデル)
8. [ネットワークアクセス](#ネットワークアクセス)
9. [lib（install/update）](#libinstallupdate)
10. [Dependency Installation (pip)](#dependency-installation-pip)
11. [Pack開発ガイド](#pack開発ガイド)
12. [InterfaceRegistry API](#interfaceregistry-api)
13. [EventBus API](#eventbus-api)
14. [監査ログ](#監査ログ)
15. [セキュリティ](#セキュリティ)
16. [トラブルシューティング](#トラブルシューティング)

---

## 設計思想

### 贔屓なし（No Favoritism）

Rumi AI の公式コードは以下の概念を**一切知りません**：

- 「チャット」「メッセージ」
- 「ツール」「プロンプト」
- 「AIクライアント」
- 「フロントエンド」

これらは全て `ecosystem/packs/` 内の Pack が定義します。公式が提供するのは：

- Flow実行エンジン（ステップ順次実行）
- InterfaceRegistry（登録箱）
- EventBus（イベント通信）
- Diagnostics（診断情報）
- 権限・承認システム

### Flow中心

Pack間の結線・順序・後付け注入（tool等）をFlowで行い、既存Pack（ai_client等）の改造なしに進化へ追随できます。

```
┌─────────────────────────────────────────────────────────────┐
│                        Flow                                  │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│  │ Block A │───▶│ Block B │───▶│ Block C │                 │
│  │(Pack X) │    │(Pack Y) │    │(Pack Z) │                 │
│  └─────────┘    └─────────┘    └─────────┘                 │
│       │              │              │                       │
│       ▼              ▼              ▼                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              InterfaceRegistry                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 悪意Pack前提

ecosystemは第三者が作り、マルウェア作者もいます。したがって：

- **承認必須**: 未承認Packのコードは実行されない
- **ハッシュ検証**: 変更があれば再承認が必要
- **Docker隔離**: strictモードではコンテナ内で実行
- **ネットワーク制御**: 明示的なGrant必要

### Fail-Soft

エラーが発生してもシステムは停止しません。失敗したコンポーネントは無効化され、診断情報に記録されて継続します。

---

## アーキテクチャ概要

### コア層

```
core_runtime/
├── kernel.py              # Flow実行エンジン
├── flow_loader.py         # Flow YAMLローダー
├── flow_modifier.py       # Flow modifier適用
├── python_file_executor.py # python_file_call実行
├── interface_registry.py  # サービス登録箱
├── event_bus.py           # イベント通信
├── diagnostics.py         # 診断情報
├── approval_manager.py    # Pack承認管理
├── network_grant_manager.py # ネットワーク権限
├── egress_proxy.py        # 外部通信プロキシ
├── lib_executor.py        # lib install/update
└── audit_logger.py        # 監査ログ
```

### 実行フロー

```
起動
  │
  ▼
┌─────────────────────┐
│ 1. Flow読み込み      │ flows/, ecosystem/flows/
└─────────────────────┘
  │
  ▼
┌─────────────────────┐
│ 2. Modifier適用      │ ecosystem/flows/modifiers/
└─────────────────────┘
  │
  ▼
┌─────────────────────┐
│ 3. 承認チェック      │ 未承認Packはスキップ
└─────────────────────┘
  │
  ▼
┌─────────────────────┐
│ 4. lib処理          │ install.py / update.py
└─────────────────────┘
  │
  ▼
┌─────────────────────┐
│ 5. Flow実行         │ python_file_call等
└─────────────────────┘
```

---

## ディレクトリ構造

### 完成後の構造

```
project_root/
├── app.py
├── bootstrap.py
├── requirements.txt
│
├── core_runtime/              # カーネル（実行エンジン）
│
├── backend_core/              # エコシステム基盤
│   └── ecosystem/
│
├── flows/                     # ★公式Flow（起動・基盤）
│   └── 00_startup.flow.yaml
│
├── ecosystem/
│   ├── flows/                 # ★ecosystem Flow（共有の結線）
│   │   ├── ai_response.flow.yaml
│   │   └── ...
│   │
│   ├── flows/modifiers/       # ★差し込み定義（Flow modifier）
│   │   ├── tool_inject.modifier.yaml
│   │   └── ...
│   │
│   └── packs/                 # Pack格納
│       └── {pack_id}/
│           └── backend/
│               ├── ecosystem.json
│               ├── permissions.json
│               ├── components/
│               │   └── {component_id}/
│               │       ├── manifest.json
│               │       ├── setup.py
│               │       └── blocks/        # ★python_file_callブロック
│               │           ├── generate.py
│               │           └── ...
│               └── lib/                   # ★lib（整理目的）
│                   ├── install.py
│                   └── update.py
│
├── user_data/
│   ├── permissions/
│   │   ├── approvals/         # Pack承認状態
│   │   ├── network/           # ネットワークGrant
│   │   └── .secret_key
│   ├── audit/                 # 監査ログ
│   │   ├── flow_execution_YYYY-MM-DD.jsonl
│   │   ├── python_file_call_YYYY-MM-DD.jsonl
│   │   └── network_YYYY-MM-DD.jsonl
│   ├── settings/
│   │   └── lib_execution_records.json
│   └── ...
│
└── docs/
```

---

## Flowシステム

### Flow YAMLフォーマット

```yaml
# {flow_id}.flow.yaml

flow_id: ai_response           # 必須: Flow識別子
inputs:                        # 必須: 入力定義
  user_input: string
  context: object
outputs:                       # 必須: 出力定義
  response: string

phases:                        # 必須: フェーズ一覧（実行順序）
  - prepare
  - generate
  - postprocess

defaults:                      # 任意: デフォルト設定
  fail_soft: true
  on_missing_step: skip

steps:                         # 必須: ステップ定義
  - id: step_1
    phase: prepare
    priority: 10
    type: handler
    input:
      handler: "kernel:ctx.get"
      args:
        key: "context"
    output: context
```

### ステップタイプ

| タイプ | 説明 | 主なフィールド |
|--------|------|----------------|
| `handler` | 既存のKernel/IRハンドラを呼び出し | `input.handler`, `input.args` |
| `python_file_call` | Pythonファイルを実行 | `file`, `owner_pack`, `input` |
| `set` | コンテキストに値を設定 | `input.key`, `input.value` |
| `if` | 条件分岐（簡易） | `input.condition` |

### 実行順序

Flowの実行順は**必ず決定的**です：

1. `phases` の並び順でソート
2. 同じphase内は `priority` 昇順（小さいほど先）
3. priorityが同値の場合は `id` 昇順

### 変数参照

```yaml
input:
  user_id: "${ctx.user.id}"      # ネスト参照
  settings: "${ctx.config}"       # オブジェクト全体
```

参照できない場合は `null` 扱い（fail-soft）。

---

## python_file_call（ブロック実行）

### 概要

Flowの結線として、任意のPythonブロックを実行し、入力→出力で次に繋ぎます。

### Step定義

```yaml
- id: generate_response
  phase: generate
  priority: 50
  type: python_file_call
  owner_pack: ai_client          # 任意: 所有Pack（パスから推測可能）
  file: blocks/generate.py       # 必須: 実行ファイル
  input:                         # 任意: 入力データ
    user_input: "${ctx.user_input}"
    context: "${ctx.context}"
  output: ai_output              # 任意: 結果格納先
  timeout_seconds: 60            # 任意: タイムアウト
```

### Python側の実装

```python
# blocks/generate.py

def run(input_data, context=None):
    """
    メイン実行関数
    
    Args:
        input_data: Flowから渡される入力データ
        context: 実行コンテキスト
            - flow_id: Flow ID
            - step_id: ステップID
            - phase: フェーズ名
            - ts: タイムスタンプ
            - owner_pack: 所有Pack ID
            - inputs: 入力データ
            - network_check: ネットワークチェック関数
            - http_request: HTTP リクエスト関数（プロキシ経由）
    
    Returns:
        JSON互換の出力データ
    """
    user_input = input_data.get("user_input", "")
    
    # 処理...
    
    return {
        "text": "Generated response",
        "tokens": 100
    }
```

### context で提供される関数

#### network_check(domain, port)

ネットワークアクセスが許可されているかチェック：

```python
def run(input_data, context):
    check = context.get("network_check")
    result = check("api.example.com", 443)
    
    if not result["allowed"]:
        return {"error": result["reason"]}
    
    # アクセス可能
```

#### http_request(method, url, headers, body, timeout_seconds)

Egress Proxy経由でHTTPリクエストを送信：

```python
def run(input_data, context):
    http = context.get("http_request")
    
    result = http(
        method="GET",
        url="https://api.example.com/data",
        headers={"Accept": "application/json"},
        timeout_seconds=10.0
    )
    
    if result["success"]:
        return {"data": result["body"]}
    else:
        return {"error": result["error"]}
```

### セキュリティ制約

1. **承認必須**: 未承認Packのコードは実行されない
2. **ハッシュ検証**: Modifiedなpackのコードは実行されない
3. **パス制限**: `ecosystem/packs/` 配下のみ実行可能
4. **Docker隔離**: strictモードではコンテナ内で実行

---

## Flow Modifier（差し込み）

### 概要

Pack同士が互いを知らなくても、Flowに後から差し込めます。

### Modifier YAMLフォーマット

```yaml
# {modifier_id}.modifier.yaml

modifier_id: tool_inject         # 必須: 全体で一意
target_flow_id: ai_response      # 必須: 対象Flow
phase: prepare                   # 必須: 差し込みフェーズ
priority: 50                     # 任意: デフォルト100

action: inject_after             # 必須: 操作タイプ
target_step_id: load_context     # 操作により必須

requires:                        # 任意: 適用条件
  capabilities:
    - tool_support
  interfaces:
    - tool.registry

step:                            # inject/append/replaceで必須
  id: inject_tools
  type: python_file_call
  owner_pack: tool_pack
  file: blocks/tool_selector.py
  input:
    context: "${ctx.context}"
  output: selected_tools
```

### Action タイプ

| Action | 説明 | target_step_id | step |
|--------|------|----------------|------|
| `inject_before` | 指定ステップの前に挿入 | 必須 | 必須 |
| `inject_after` | 指定ステップの後に挿入 | 必須 | 必須 |
| `append` | フェーズの末尾に追加 | 不要 | 必須 |
| `replace` | 指定ステップを置換 | 必須 | 必須 |
| `remove` | 指定ステップを削除 | 必須 | 不要 |

### requires 条件

```yaml
requires:
  interfaces:              # IRに登録されているキー
    - ai.client
    - tool.registry
  capabilities:            # component.capabilitiesに登録された値
    - tool_support
    - streaming
```

条件が満たされない場合、modifierはスキップされます（fail-soft）。

### 適用順序

1. `phase` 順
2. `priority` 昇順
3. `modifier_id` 昇順

---

## 権限モデル

### Pack承認フロー

```
Pack配置 (ecosystem/packs/)
    │
    ▼
メタデータのみ読み込み（コード実行なし）
    │
    ▼
ユーザー承認
    │
    ▼
全ファイルの SHA-256 ハッシュを記録
    │
    ▼
初めてコード実行
```

### 承認状態

| 状態 | 説明 | コード実行 |
|------|------|-----------|
| `installed` | 配置済み、未承認 | ❌ |
| `pending` | 承認待ち | ❌ |
| `approved` | 承認済み | ✅ |
| `modified` | 承認後に変更あり | ❌ |
| `blocked` | 拒否済み | ❌ |

### ハッシュ検証

承認時に全ファイルのSHA-256ハッシュを記録。起動時にハッシュを検証し、不一致の場合は `modified` 状態となり、再承認が必要です。

---

## ネットワークアクセス

### 設計原則

- Packは直接外部通信できない（Docker `network=none`）
- 全ての外部通信は Egress Proxy を経由
- `owner_pack` の network grant で allow/deny を判定
- 全リクエストを監査ログに記録

### Network Grant

```json
// user_data/permissions/network/{pack_id}.json
{
  "pack_id": "my_pack",
  "enabled": true,
  "allowed_domains": [
    "api.openai.com",
    "*.anthropic.com"
  ],
  "allowed_ports": [443, 80],
  "granted_at": "2024-01-01T00:00:00Z",
  "granted_by": "user"
}
```

### ドメインマッチング

- 完全一致: `api.openai.com`
- ワイルドカード: `*.anthropic.com` （サブドメイン許可）
- サブドメイン許可: `openai.com` は `api.openai.com` も許可

### Kernelハンドラ

```yaml
# Grant付与
- type: handler
  input:
    handler: "kernel:network.grant"
    args:
      pack_id: "my_pack"
      allowed_domains: ["api.openai.com"]
      allowed_ports: [443]

# アクセスチェック
- type: handler
  input:
    handler: "kernel:network.check"
    args:
      pack_id: "my_pack"
      domain: "api.openai.com"
      port: 443
```

### Modified時の自動無効化

Packが `modified` 状態になると、ネットワーク権限は自動的に無効化されます。再承認後に再有効化されます。

---

## lib（install/update）

### 概要

libは「整理」目的。インストール/更新時だけ実行され、普段は停止しています。

### ディレクトリ構造

```
{pack_id}/
└── backend/
    └── lib/
        ├── install.py    # 初回導入時に実行
        └── update.py     # ハッシュ変更時に実行
```

### 実行タイミング

| 条件 | 実行されるファイル |
|------|-------------------|
| 初回導入（記録なし） | `install.py` |
| ハッシュ変更 | `update.py`（なければ`install.py`） |
| 変更なし | 実行しない |

### 実装例

```python
# lib/install.py

def run(context=None):
    """
    初回インストール処理
    
    Args:
        context:
            - pack_id: Pack ID
            - lib_type: "install"
            - ts: タイムスタンプ
            - lib_dir: libディレクトリパス
    """
    pack_id = context.get("pack_id") if context else "unknown"
    
    # 初期化処理
    # - 設定ファイル作成
    # - データベース初期化
    # - 依存関係のセットアップ
    
    return {"status": "installed"}
```

```python
# lib/update.py

def run(context=None):
    """
    アップデート処理
    """
    pack_id = context.get("pack_id") if context else "unknown"
    
    # マイグレーション処理
    # - スキーマ更新
    # - データ変換
    
    return {"status": "updated"}
```

### セキュリティ

- 承認済みPackのみ実行可能
- Modifiedなら実行されない

---

## Dependency Installation (pip)

### 概要

Pack が PyPI パッケージに依存する場合、`requirements.lock` を同梱し、API で承認するとビルダー用 Docker コンテナで安全にインストールされます。ホスト Python 環境は汚れません。

### requirements.lock の置き場所

pack_subdir 基準で探索されます:

1. `<pack_subdir>/requirements.lock`
2. `<pack_subdir>/backend/requirements.lock`（互換）

### 承認フロー

```
scan → pending → approve → installed
                → reject  → rejected (cooldown 1h)
                            → 3回 reject → blocked
                                            → unblock → pending
```

### 生成物

```
user_data/packs/<pack_id>/python/
├── wheelhouse/         # ダウンロードしたファイル
├── site-packages/      # インストール展開先
└── state.json          # メタデータ
```

### 実行時の import

site-packages が存在する場合、実行コンテナに `/pip-packages:ro` としてマウントされ、`PYTHONPATH` に追加されます。Pack コードからは通常通り `import` するだけです。

### 詳細ドキュメント

- [Pip Dependency Installation 完成像](pip_dependency_installation.md)
- [requirements.lock 規約](spec/requirements_lock.md)
- [運用手順](runbook/dependency_workflow.md)
- [PYTHONPATH と site-packages 仕様](architecture/pythonpath_and_sitepackages.md)

---

## Pack開発ガイド

### 最小構成

```
ecosystem/packs/my_pack/
└── backend/
    ├── ecosystem.json
    └── blocks/
        └── hello.py
```

### ecosystem.json

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "version": "1.0.0",
  "description": "My first pack"
}
```

### ブロック実装

```python
# blocks/hello.py

def run(input_data, context=None):
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

### Flow定義

```yaml
# ecosystem/flows/hello.flow.yaml

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

### 権限要求（permissions.json）

```json
{
  "pack_id": "my_pack",
  "permissions": [
    {
      "type": "network",
      "domains": ["api.example.com"],
      "ports": [443],
      "reason": "外部APIにアクセスするため"
    }
  ]
}
```

---

## InterfaceRegistry API

### 基本操作

```python
# 登録
ir.register("my.service", handler, meta={"version": "1.0"})

# 取得
service = ir.get("my.service")                    # 最新
service = ir.get("my.service", strategy="first")  # 最初
services = ir.get("my.service", strategy="all")   # 全て（[]）

# handler登録（スキーマ付き）
ir.register_handler(
    "api.users.create",
    handler,
    input_schema={...},
    output_schema={...}
)
```

### Observer（変更監視）

```python
def on_change(key, old_value, new_value):
    print(f"{key}: {old_value} -> {new_value}")

observer_id = ir.observe("state.*", on_change)
ir.unobserve(observer_id)
```

### 一時的な上書き

```python
with ir.temporary_override("ai.client", mock_client):
    # ここではmock_clientが使われる
    result = ir.get("ai.client")(args, ctx)
# 元に戻る
```

---

## EventBus API

```python
# 購読
handler_id = eb.subscribe("user.created", on_user_created)

# 発行
eb.publish("user.created", {"user_id": "123"})

# 購読解除
eb.unsubscribe("user.created", handler_id)
```

---

## 監査ログ

### カテゴリ

| カテゴリ | 説明 | ファイル |
|---------|------|----------|
| `flow_execution` | Flow実行 | `flow_execution_YYYY-MM-DD.jsonl` |
| `modifier_application` | Modifier適用 | `modifier_application_YYYY-MM-DD.jsonl` |
| `python_file_call` | ブロック実行 | `python_file_call_YYYY-MM-DD.jsonl` |
| `approval` | 承認操作 | `approval_YYYY-MM-DD.jsonl` |
| `permission` | 権限操作 | `permission_YYYY-MM-DD.jsonl` |
| `network` | ネットワーク | `network_YYYY-MM-DD.jsonl` |
| `security` | セキュリティ | `security_YYYY-MM-DD.jsonl` |
| `system` | システム | `system_YYYY-MM-DD.jsonl` |

### エントリ形式

```json
{
  "ts": "2024-01-01T00:00:00Z",
  "category": "python_file_call",
  "severity": "info",
  "action": "execute_python_file",
  "success": true,
  "flow_id": "ai_response",
  "step_id": "generate",
  "phase": "generate",
  "owner_pack": "ai_client",
  "execution_mode": "host_permissive",
  "details": {
    "file": "blocks/generate.py",
    "execution_time_ms": 150.5
  }
}
```

### Kernelハンドラ

```yaml
# ログ検索
- type: handler
  input:
    handler: "kernel:audit.query"
    args:
      category: "network"
      pack_id: "my_pack"
      limit: 100

# サマリー取得
- type: handler
  input:
    handler: "kernel:audit.summary"
    args:
      date: "2024-01-01"
```

---

## セキュリティ

### セキュリティモード

環境変数 `RUMI_SECURITY_MODE` で設定：

| モード | Docker | 未承認Pack | 説明 |
|--------|--------|-----------|------|
| `strict` | 必須 | 実行拒否 | 本番推奨 |
| `permissive` | 不要 | 警告付き実行 | 開発用 |

### 保護機構

| 機構 | 説明 |
|------|------|
| 承認ゲート | 未承認Packのコードは実行されない |
| ハッシュ検証 | 承認後にファイル変更されると無効化 |
| HMAC署名 | grants.jsonの改ざんを検出 |
| パス制限 | 許可ディレクトリ外のファイル実行を拒否 |
| Egress Proxy | 外部通信をallow listで制御 |
| 監査ログ | 全操作を記録 |

### 脅威対策

| 脅威 | 対策 |
|------|------|
| 悪意あるコード実行 | 承認必須 + Docker隔離 |
| ファイル改ざん | SHA-256ハッシュ検証 |
| 設定改ざん | HMAC署名 |
| 不正な外部通信 | Egress Proxy + allow list |
| 権限昇格 | Pack単位の明示的Grant |

---

## トラブルシューティング

### Packが実行されない

```bash
# 承認状態を確認
curl http://localhost:8765/api/packs/{pack_id}/status

# 承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve
```

### Packが無効化された

ファイルが変更されるとハッシュ不一致で `modified` 状態になります。再承認が必要です。

### ネットワークアクセスが拒否される

```yaml
# Grantを確認
- type: handler
  input:
    handler: "kernel:network.list"

# Grantを付与
- type: handler
  input:
    handler: "kernel:network.grant"
    args:
      pack_id: "my_pack"
      allowed_domains: ["api.example.com"]
      allowed_ports: [443]
```

### Modifierが適用されない

1. `target_flow_id` が正しいか確認
2. `phase` がFlowに存在するか確認
3. `requires` の条件が満たされているか確認

診断ログで確認：

```yaml
- type: handler
  input:
    handler: "kernel:audit.query"
    args:
      category: "modifier_application"
```

### libが実行されない

```yaml
# 記録を確認
- type: handler
  input:
    handler: "kernel:lib.list_records"

# 強制再実行
- type: handler
  input:
    handler: "kernel:lib.clear_record"
    args:
      pack_id: "my_pack"
```

### Docker関連エラー

```
Error: Docker is required but not available
```

1. Docker Desktop が起動しているか確認
2. 開発時は `RUMI_SECURITY_MODE=permissive` を設定

---

## Kernelハンドラ一覧

### Flow関連

| ハンドラ | 説明 |
|---------|------|
| `kernel:flow.load_all` | 全Flowをロード |
| `kernel:flow.execute_by_id` | Flow IDで実行 |

### Modifier関連

| ハンドラ | 説明 |
|---------|------|
| `kernel:modifier.load_all` | 全Modifierをロード |
| `kernel:modifier.apply` | Modifierを適用 |

### 権限関連

| ハンドラ | 説明 |
|---------|------|
| `kernel:network.grant` | ネットワーク権限を付与 |
| `kernel:network.revoke` | ネットワーク権限を取り消し |
| `kernel:network.check` | アクセス可否をチェック |
| `kernel:network.list` | 全Grantを一覧 |

### Egress Proxy関連

| ハンドラ | 説明 |
|---------|------|
| `kernel:egress_proxy.start` | プロキシを起動 |
| `kernel:egress_proxy.stop` | プロキシを停止 |
| `kernel:egress_proxy.status` | 状態を取得 |

### lib関連

| ハンドラ | 説明 |
|---------|------|
| `kernel:lib.process_all` | 全Packのlibを処理 |
| `kernel:lib.check` | 実行が必要かチェック |
| `kernel:lib.execute` | 手動実行 |
| `kernel:lib.clear_record` | 記録をクリア |
| `kernel:lib.list_records` | 記録を一覧 |

### 監査関連

| ハンドラ | 説明 |
|---------|------|
| `kernel:audit.query` | ログを検索 |
| `kernel:audit.summary` | サマリーを取得 |
| `kernel:audit.flush` | バッファをフラッシュ |

### コンテキスト操作

| ハンドラ | 説明 |
|---------|------|
| `kernel:ctx.set` | 値を設定 |
| `kernel:ctx.get` | 値を取得 |
| `kernel:ctx.copy` | 値をコピー |
| `kernel:noop` | 何もしない |

---

## 付録: 完全なPack例

### ディレクトリ構造

```
ecosystem/packs/ai_client/
└── backend/
    ├── ecosystem.json
    ├── permissions.json
    ├── blocks/
    │   └── generate.py
    └── lib/
        ├── install.py
        └── update.py
```

### ecosystem.json

```json
{
  "pack_id": "ai_client",
  "pack_identity": "github:author/ai_client",
  "version": "1.0.0",
  "description": "AI client for OpenAI API"
}
```

### permissions.json

```json
{
  "pack_id": "ai_client",
  "permissions": [
    {
      "type": "network",
      "domains": ["api.openai.com"],
      "ports": [443],
      "reason": "OpenAI APIにアクセスするため"
    }
  ]
}
```

### blocks/generate.py

```python
"""
AI応答生成ブロック
"""

def run(input_data, context=None):
    """
    OpenAI APIを使用して応答を生成
    """
    if not context:
        return {"error": "No context provided"}
    
    http_request = context.get("http_request")
    if not http_request:
        return {"error": "http_request not available"}
    
    messages = input_data.get("messages", [])
    model = input_data.get("model", "gpt-4")
    
    # APIキーは別途設定から取得する想定
    api_key = input_data.get("api_key", "")
    
    result = http_request(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        body=json.dumps({
            "model": model,
            "messages": messages
        }),
        timeout_seconds=60.0
    )
    
    if not result.get("success"):
        return {
            "error": result.get("error"),
            "allowed": result.get("allowed", False)
        }
    
    import json
    response_data = json.loads(result.get("body", "{}"))
    
    return {
        "text": response_data.get("choices", [{}])[0].get("message", {}).get("content", ""),
        "usage": response_data.get("usage", {})
    }
```

### Flow定義 (ecosystem/flows/ai_response.flow.yaml)

```yaml
flow_id: ai_response
inputs:
  messages: array
  model: string
  api_key: string
outputs:
  response: object

phases:
  - prepare
  - generate
  - postprocess

defaults:
  fail_soft: true

steps:
  - id: validate_input
    phase: prepare
    priority: 10
    type: handler
    input:
      handler: "kernel:ctx.get"
      args:
        key: "messages"
        default: []
    output: validated_messages

  - id: generate_response
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      messages: "${ctx.validated_messages}"
      model: "${ctx.model}"
      api_key: "${ctx.api_key}"
    output: ai_result

  - id: format_output
    phase: postprocess
    priority: 10
    type: set
    input:
      key: response
      value: "${ctx.ai_result}"
```

### Modifier例 (ecosystem/flows/modifiers/add_logging.modifier.yaml)

```yaml
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
    flow_id: "${ctx._flow_id}"
```

---

*「Flowが中心、贔屓なし、悪意Pack前提」— これがRumi AI Ecosystemの設計原則です。*
```