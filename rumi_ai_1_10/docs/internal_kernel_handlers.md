

```markdown
# Rumi AI OS

**「基盤のない基盤」** - 改造される「本体」が存在しないモジュラーAIフレームワーク

---

## 思想

### 贔屓なし（No Favoritism）

Rumi AI の公式コードは以下の概念を**一切知りません**：

- 「チャット」「メッセージ」
- 「ツール」「プロンプト」
- 「AIクライアント」
- 「フロントエンド」

これらは全て `ecosystem/packs/` 内の Pack が定義します。公式が提供するのは**実行の仕組み**だけです。

### Flow中心アーキテクチャ

Rumi AI はFlowを中心としたアーキテクチャを採用しています：

- **Pack間の結線・順序・後付け注入をFlowで定義**
- **既存Packの改造なしに新機能を追加可能**
- **modifier による動的なFlow拡張**

```
┌─────────────────────────────────────────────────────────────┐
│                        Flow定義                              │
│  (flows/, user_data/shared/flows/,                          │
│   ecosystem/<pack_id>/backend/flows/)                       │
├─────────────────────────────────────────────────────────────┤
│                     python_file_call                         │
│              (Pack内のブロックを実行)                         │
├─────────────────────────────────────────────────────────────┤
│    Pack A         Pack B         Pack C                      │
│   (blocks/)      (blocks/)      (blocks/)                    │
├─────────────────────────────────────────────────────────────┤
│                      Kernel                                  │
│            (実行エンジン・セキュリティ)                       │
└─────────────────────────────────────────────────────────────┘
```

### 基盤のない基盤

Minecraft の mod は「Minecraft」という基盤を改造します。しかし Rumi AI には改造される「本体」がありません。

### Fail-Soft

エラーが発生してもシステムは停止しません。失敗したコンポーネントは無効化され、診断情報に記録されて継続します。

### 悪意Pack前提のセキュリティ

ecosystemは第三者が作成でき、悪意ある作者も存在しうるという前提で設計されています：

- **承認必須**: 未承認Packのコードは一切実行されない
- **ハッシュ検証**: 承認後にファイルが変更されると自動無効化（再承認必要）
- **Docker隔離**: 承認済みPackはコンテナ内で実行
- **Egress Proxy**: 外部通信はプロキシ経由のみ許可

---

## ディレクトリ構造

```
project_root/
│
├── app.py                      # OS エントリポイント
├── bootstrap.py                # セットアップエントリポイント
├── requirements.txt            # Python 依存関係
│
├── core_runtime/               # カーネル（実行エンジン）
│   ├── kernel.py               # Flow実行エンジン
│   ├── flow_loader.py          # Flow YAMLローダー
│   ├── flow_modifier.py        # Flow modifier適用
│   ├── python_file_executor.py # python_file_call実行
│   ├── approval_manager.py     # Pack承認管理
│   ├── network_grant_manager.py # ネットワーク権限管理
│   ├── egress_proxy.py         # 外部通信プロキシ
│   ├── capability_proxy.py     # Host Capability Proxy
│   ├── capability_grant_manager.py # Capability Grant管理
│   ├── capability_installer.py # Capability Handler候補導入
│   ├── pip_installer.py        # pip依存ライブラリ導入
│   ├── lib_executor.py         # lib install/update実行
│   ├── audit_logger.py         # 監査ログ
│   ├── pack_applier.py         # Pack apply（staging→ecosystem）
│   ├── pack_importer.py        # Pack import（zip/folder→staging）
│   ├── secrets_store.py        # Secrets管理
│   ├── interface_registry.py   # 内部サービス登録（Pack非公開）
│   ├── event_bus.py            # イベント通信
│   ├── diagnostics.py          # 診断情報
│   ├── paths.py                # パス解決ユーティリティ
│   ├── rumi_syscall.py         # コンテナ内syscall API
│   ├── rumi_capability.py      # コンテナ内capability API
│   ├── shared_dict/            # 共有辞書システム
│   │   ├── __init__.py
│   │   ├── snapshot.py         # スナップショット管理
│   │   ├── journal.py          # ジャーナル管理
│   │   └── resolver.py         # 解決エンジン
│   └── ...
│
├── backend_core/               # エコシステム基盤
│   └── ecosystem/
│       ├── registry.py         # Pack/Component読み込み
│       ├── mounts.py           # パス抽象化
│       └── ...
│
├── flows/                      # 公式Flow（起動・基盤）
│   └── 00_startup.flow.yaml
│
├── ecosystem/                  # Pack格納
│   └── packs/
│       └── {pack_id}/
│           └── backend/
│               ├── ecosystem.json
│               ├── permissions.json
│               ├── blocks/     # python_file_callブロック
│               ├── flows/      # Pack提供のFlow
│               ├── lib/        # install.py, update.py
│               ├── share/
│               │   └── capability_handlers/  # Capability handler候補
│               ├── vocab.txt   # 同義語グループ（任意）
│               └── converters/ # 変換器（任意）
│
├── user_data/
│   ├── shared/
│   │   ├── flows/              # 共有Flow（外部ツール/packが配置可能）
│   │   │   └── *.flow.yaml
│   │   └── flows/modifiers/    # Flow modifier
│   │       └── *.modifier.yaml
│   ├── permissions/
│   │   ├── approvals/          # Pack承認状態
│   │   ├── network/            # ネットワーク権限
│   │   ├── capabilities/       # Capability Grant
│   │   └── .secret_key
│   ├── capabilities/
│   │   ├── handlers/           # 実働Capability handler
│   │   ├── trust/              # Trust store（sha256 allowlist）
│   │   └── requests/           # 候補申請・履歴
│   ├── secrets/                # Secrets（1 key = 1 file）
│   ├── audit/                  # 監査ログ
│   ├── pending/                # 承認待ち状況サマリー
│   │   └── summary.json        # kernel:pending.export が生成
│   ├── packs/                  # Pack別データ（lib RW用）
│   │   └── {pack_id}/
│   │       └── python/         # pip依存（site-packages等）
│   ├── pip/
│   │   └── requests/           # pip候補申請・履歴
│   ├── settings/
│   │   ├── shared_dict/        # 共有辞書データ
│   │   │   ├── snapshot.json
│   │   │   └── journal.jsonl
│   │   └── lib_execution_records.json
│   ├── pack_staging/           # Pack import staging
│   ├── pack_backups/           # Pack apply バックアップ
│   └── ...
│
└── docs/
    └── internal_kernel_handlers.md  # 内部ハンドラ一覧
```

**注意**: `flow/` ディレクトリおよび `ecosystem/flows/` は非推奨です。新規Flowは `flows/`、`user_data/shared/flows/`、または Pack内の `flows/` に配置してください。

---

## Flow 読み込み元

| 優先度 | パス | 用途 |
|--------|------|------|
| 1 | `flows/` | 公式Flow（起動・基盤） |
| 2 | `user_data/shared/flows/` | ユーザー/外部ツールが配置する共有Flow |
| 3 | `ecosystem/<pack_id>/backend/flows/` | Pack提供のFlow |
| (deprecated) | `ecosystem/flows/` | local_pack互換（オプトイン、非推奨） |

`ecosystem/flows/` は `RUMI_LOCAL_PACK_MODE=require_approval` でのみ有効です。デフォルトでは無効（off）です。

---

## Flow システム

### Flow ファイル形式

```yaml
# user_data/shared/flows/ai_response.flow.yaml

flow_id: ai_response
inputs:
  user_input: string
  context: object
outputs:
  response: string

phases:
  - prepare
  - generate
  - postprocess

defaults:
  fail_soft: true
  on_missing_step: skip

steps:
  - id: load_context
    phase: prepare
    priority: 10
    type: handler
    input:
      handler: "kernel:ctx.get"
      args:
        key: "context"

  - id: call_ai
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      user_input: "${ctx.user_input}"
    output: ai_response
```

### ステップタイプ

| type | 説明 |
|------|------|
| `handler` | 既存のKernelハンドラを呼び出し |
| `python_file_call` | Pack内のPythonファイルを実行 |
| `set` | コンテキストに値を設定 |
| `if` | 条件分岐（簡易版） |

### 実行順序

ステップは以下の順序で決定的にソートされます：

1. `phase`（phases配列での順序）
2. `priority`（昇順、小さいほど先）
3. `id`（アルファベット順、タイブレーク）

---

## Flow Modifier

既存Flowに後からステップを注入・置換・削除できます。

```yaml
# user_data/shared/flows/modifiers/tool_inject.modifier.yaml

modifier_id: tool_inject
target_flow_id: ai_response
phase: prepare
priority: 50
action: inject_after
target_step_id: load_context

requires:
  capabilities:
    - tool_support

step:
  id: inject_tools
  type: python_file_call
  owner_pack: tool_pack
  file: blocks/tool_selector.py
  input:
    context: "${ctx.context}"
  output: selected_tools
```

### アクション

| action | 説明 |
|--------|------|
| `inject_before` | target_step_idの前に挿入 |
| `inject_after` | target_step_idの後に挿入 |
| `append` | phaseの末尾に追加 |
| `replace` | target_step_idを置換 |
| `remove` | target_step_idを削除 |

### requires条件

```yaml
requires:
  interfaces:
    - "ai.client"           # IRに登録されているか
  capabilities:
    - "tool_support"        # capabilityが有効か
```

### resolve_target（共有辞書での解決）

```yaml
# target_flow_id を共有辞書で解決する場合
modifier_id: compat_modifier
target_flow_id: old_flow_name
resolve_target: true              # オプトイン
resolve_namespace: "flow_id"      # デフォルト
```

---

## python_file_call

Pack内のPythonファイルを実行します。

### ブロックファイルの形式

```python
# ecosystem/packs/my_pack/backend/blocks/my_block.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flowから渡される入力
        context: 実行コンテキスト
            - flow_id, step_id, phase, ts
            - owner_pack
            - inputs
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> ProxyResponse
    
    Returns:
        JSON互換の出力データ
    """
    # 外部API呼び出し例
    http_request = context.get("http_request")
    if http_request:
        result = http_request(
            method="GET",
            url="https://api.example.com/data",
            headers={"Accept": "application/json"}
        )
        if result["success"]:
            return {"data": result["body"]}
    
    return {"message": "Hello from my_block!"}
```

### セキュリティ

- **承認チェック**: owner_packが承認済みでなければ実行拒否
- **ハッシュ検証**: Packが変更されていたら実行拒否
- **パス制限**: 許可されたディレクトリ外のファイルは実行拒否
- **ネットワーク制限**: Egress Proxy経由でのみ外部通信可能

### principal_id の扱い（v1）

v1 では、`principal_id` は常に `owner_pack` に強制上書きされます。Flow定義で `principal_id` を指定しても、実行時は `owner_pack` が使用されます。これは権限の乱用事故を防ぐための措置です。

将来のバージョンで principal_id の独立運用が検討される場合があります。監査ログには `principal_id_overridden` として警告が記録されます。

---

## セキュリティモデル

### Pack承認フロー

```
Pack配置 (ecosystem/packs/)
    ↓
メタデータのみ読み込み（コード実行なし）
    ↓
ユーザー承認
    ↓
全ファイルのSHA-256ハッシュを記録
    ↓
初めてコード実行
```

### ネットワーク権限

```yaml
# Kernel handler で Grant 付与
- type: handler
  input:
    handler: "kernel:network.grant"
    args:
      pack_id: "my_pack"
      allowed_domains: ["api.example.com", "*.openai.com"]
      allowed_ports: [443]
```

HTTP API でも操作可能です（後述の「HTTP API」セクション参照）。

### Egress Proxy

Packは直接外部通信できません。全ての通信はEgress Proxyを経由します：

```
Pack (network=none) → UDS Socket → Egress Proxy → 外部API
                                        ↓
                                  network grant確認
                                        ↓
                                    監査ログ記録
```

### UDS ソケット権限と --group-add

strict モードで UDS ソケット（0660）にコンテナからアクセスするには、専用 GID の設定が必要です：

1. 専用 GID を決定（例: 1099）
2. 環境変数を設定:
   ```bash
   export RUMI_EGRESS_SOCKET_GID=1099
   export RUMI_CAPABILITY_SOCKET_GID=1099
   ```
3. ソケット作成時に自動的に指定 GID の group が設定されます
4. docker run 時に `--group-add=1099` が自動付与されます

GID が未設定の場合、ソケットは root:root で 0660 になりうるため、コンテナ（nobody:65534）からアクセスできません。最終手段として `RUMI_EGRESS_SOCKET_MODE=0666` / `RUMI_CAPABILITY_SOCKET_MODE=0666` で緩和可能ですが非推奨です。

### セキュリティモード

環境変数 `RUMI_SECURITY_MODE` で設定：

| モード | Docker | 動作 |
|--------|--------|------|
| `strict`（デフォルト） | 必須 | Docker不可なら実行拒否 |
| `permissive` | 不要 | 警告付きでホスト実行を許可（開発用） |

```bash
# 本番環境（推奨）
export RUMI_SECURITY_MODE=strict

# 開発環境
export RUMI_SECURITY_MODE=permissive
```

---

## Capability システム

### 概要

Pack が提供する capability handler を承認・実働化し、principal（主体）に対して使用権限（Grant）を付与する仕組みです。

```
候補配置 → scan → pending → approve (Trust+copy) → Grant付与 → 使用可能
```

### Trust + Grant 分離

- **Trust**: handler_id + sha256 の allowlist。handler.py の内容が信頼済みかを判定
- **Grant**: principal_id × permission_id の権限付与。誰がどの capability を使えるかを管理

approve は Trust のみを登録します。実際に使用するには別途 Grant の付与が必要です。

### Capability Grant 管理

```yaml
# Kernel handler で Grant 付与
- type: handler
  input:
    handler: "kernel:capability.grant"
    args:
      principal_id: "my_pack"
      permission_id: "fs.read"

# Grant 一覧
- type: handler
  input:
    handler: "kernel:capability.list"
    args:
      principal_id: "my_pack"

# Grant 取り消し
- type: handler
  input:
    handler: "kernel:capability.revoke"
    args:
      principal_id: "my_pack"
      permission_id: "fs.read"
```

HTTP API でも操作可能です（後述の「HTTP API」セクション参照）。

---

## Pending Export

起動時に `user_data/pending/summary.json` が自動生成されます。外部ツールはこのファイルを読むだけで承認待ち状況を把握できます。

```json
{
  "ts": "2026-02-11T15:00:00Z",
  "version": "1.0",
  "packs": {
    "pending_count": 2,
    "pending_ids": ["pack_a", "pack_b"],
    "modified_count": 0,
    "modified_ids": [],
    "blocked_count": 0,
    "blocked_ids": []
  },
  "capability": {
    "pending_count": 1,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 3
  },
  "pip": {
    "pending_count": 0,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 2
  }
}
```

公式は summary.json の消費者（default 等）を特別扱いしません。任意の外部ツール/Pack がこのファイルを読み取り可能です。

---

## Pip 依存ライブラリ導入

Pack が `requirements.lock` を同梱することで、PyPI パッケージへの依存を宣言できます。

### requirements.lock の規約

許可される形式は `NAME==VERSION` 行のみです（コメント/空行は可）。以下は禁止されます：

- `-e`（editable install）
- `git+`、`http://`、`https://`（URL/VCS参照）
- `file:`、`../`、`/`（ローカル参照）
- `--` で始まるオプション行
- `@` direct reference（PEP 440）

```
# requirements.lock の例
requests==2.31.0
flask==3.0.0
```

### 状態遷移

```
scan → pending → approve → installed
                → reject  → rejected (cooldown 1h)
                            → 3回 reject → blocked → unblock → pending
```

### セキュリティ

- wheel-only がデフォルト（`--only-binary=:all:`）。sdist は明示的に `allow_sdist: true` が必要
- ビルダーコンテナ（download）: `--network=bridge` + `--cap-drop=ALL`
- ビルダーコンテナ（install）: `--network=none`（完全オフライン）
- 実行コンテナ: site-packages は読み取り専用でマウント
- 未承認 Pack の依存導入は拒否（strict モード）
- index_url は https のみ、内部IP/localhost は拒否

---

## 共有辞書（Shared Dict）

任意の namespace/token を書き換えできる仕組みです。公式は namespace の意味を解釈しません（ecosystem が自由に決める）。

### 基本操作

```yaml
# ルールを提案
- type: handler
  input:
    handler: "kernel:shared_dict.propose"
    args:
      namespace: "flow_id"
      token: "old_flow_name"
      value: "new_flow_name"
      provenance:
        source_pack_id: "compat_pack"
        note: "Backward compatibility alias"

# 解決
- type: handler
  input:
    handler: "kernel:shared_dict.resolve"
    args:
      namespace: "flow_id"
      token: "old_flow_name"
```

### 安全機能

- **循環検出**: A→B→A のような循環は自動的に拒否
- **衝突検出**: 同じ token に異なる value を登録しようとすると拒否
- **ホップ上限**: デフォルト10ホップで解決を打ち切り
- **監査ログ**: 全ての操作を記録

---

## lib システム

Packの初期化・更新処理を管理します。

### ファイル構成

```
ecosystem/packs/my_pack/backend/lib/
├── install.py    # 初回導入時に実行
└── update.py     # ハッシュ変更時に実行
```

**セキュリティ**: lib は Docker コンテナ内で隔離実行されます（strictモード）。RW マウントは `user_data/packs/{pack_id}/` のみに限定されます。

### 実行タイミング

- **install.py**: Pack初回導入時に一度だけ
- **update.py**: Packファイル変更時に一度だけ
- **それ以外**: 実行されない（普段は停止）

### install.py の例

```python
def run(context=None):
    pack_id = context.get("pack_id") if context else "unknown"
    data_dir = context.get("data_dir") if context else None  # RW 書き込み先
    
    # 初期化処理
    # - data_dir 内に設定ファイル作成
    # - data_dir 内にデータベース初期化
    
    return {"status": "installed"}
```

---

## Secrets

API key などの秘密値を安全に管理します。

- `.env` は使用しない（事故率低減）
- `user_data/secrets/` に格納（1 key = 1 file、tombstone、journal）
- ログに秘密値を一切出さない（監査・診断とも）
- Pack に秘密ファイルを直接見せない
- 取得は capability（例: `secret.get`）経由が基本
- API は list（mask付き）/ set / delete のみ（再表示なし）

---

## Pack Import / Apply

### Import

フォルダ / `.zip` / `.rumipack`（zip互換）から Pack を staging に取り込みます。

```bash
curl -X POST http://localhost:8765/api/packs/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/my_pack.zip"}'
```

### Apply

staging から ecosystem に適用します。バックアップが自動作成されます。

```bash
curl -X POST http://localhost:8765/api/packs/apply \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"staging_id": "abc123"}'
```

**安全機能**: apply 時に `pack_id` と `pack_identity`（`ecosystem.json` の `pack_identity` フィールド）の両方を比較し、既存 Pack と不一致の場合は拒否します。

---

## HTTP API

全エンドポイントは `Authorization: Bearer YOUR_TOKEN` が必須です。

### Pack 管理

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/packs` | 全Pack一覧 |
| GET | `/api/packs/pending` | 承認待ちPack一覧 |
| GET | `/api/packs/{pack_id}/status` | Pack状態取得 |
| POST | `/api/packs/scan` | Packスキャン |
| POST | `/api/packs/{pack_id}/approve` | Pack承認 |
| POST | `/api/packs/{pack_id}/reject` | Pack拒否 |
| POST | `/api/packs/import` | Pack import |
| POST | `/api/packs/apply` | Pack apply |
| DELETE | `/api/packs/{pack_id}` | Packアンインストール |

### ネットワーク権限

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/network/list` | 全Grant一覧 |
| POST | `/api/network/grant` | ネットワーク権限を付与 |
| POST | `/api/network/revoke` | ネットワーク権限を取り消し |
| POST | `/api/network/check` | アクセス可否をチェック |

```bash
# Grant 付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'

# Grant 一覧
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"

# アクセスチェック
curl -X POST http://localhost:8765/api/network/check \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "domain": "api.example.com", "port": 443}'
```

### Capability Handler 候補

| メソッド | パス | 説明 |
|----------|------|------|
| POST | `/api/capability/candidates/scan` | 候補スキャン |
| GET | `/api/capability/requests?status=pending` | 申請一覧 |
| POST | `/api/capability/requests/{key}/approve` | 承認（Trust+copy） |
| POST | `/api/capability/requests/{key}/reject` | 却下 |
| GET | `/api/capability/blocked` | ブロック一覧 |
| POST | `/api/capability/blocked/{key}/unblock` | ブロック解除 |

### Capability Grant

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/capability/grants?principal_id=xxx` | Grant一覧 |
| POST | `/api/capability/grants/grant` | Grantを付与 |
| POST | `/api/capability/grants/revoke` | Grantを取り消し |

```bash
# Grant 付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'

# Grant 一覧
curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Grant 取り消し
curl -X POST http://localhost:8765/api/capability/grants/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### Pip 依存ライブラリ

| メソッド | パス | 説明 |
|----------|------|------|
| POST | `/api/pip/candidates/scan` | 候補スキャン |
| GET | `/api/pip/requests?status=pending` | 申請一覧 |
| POST | `/api/pip/requests/{key}/approve` | 承認＋インストール |
| POST | `/api/pip/requests/{key}/reject` | 却下 |
| GET | `/api/pip/blocked` | ブロック一覧 |
| POST | `/api/pip/blocked/{key}/unblock` | ブロック解除 |

### Secrets

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/secrets` | キー一覧（値はマスク） |
| POST | `/api/secrets/set` | 秘密値を設定 |
| POST | `/api/secrets/delete` | 秘密値を削除 |

### Docker / コンテナ

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/docker/status` | Docker利用可否 |
| GET | `/api/containers` | コンテナ一覧 |
| POST | `/api/containers/{pack_id}/start` | コンテナ起動 |
| POST | `/api/containers/{pack_id}/stop` | コンテナ停止 |
| DELETE | `/api/containers/{pack_id}` | コンテナ削除 |

---

## 監査ログ

全ての重要な操作が `user_data/audit/` に記録されます。

### カテゴリ

| カテゴリ | 内容 |
|----------|------|
| `flow_execution` | Flow実行 |
| `modifier_application` | modifier適用 |
| `python_file_call` | ブロック実行 |
| `approval` | Pack承認操作 |
| `permission` | 権限操作（network grant, capability grant含む） |
| `network` | ネットワーク通信 |
| `security` | セキュリティイベント |
| `system` | システムイベント（lib, pip, pending export等） |

### 日付ローテーション

監査ログはエントリの `ts`（タイムスタンプ）に基づいて正しい日付のファイルに書き込まれます。深夜跨ぎでも `2026-01-31` のエントリは `category_2026-01-31.jsonl` に、`2026-02-01` のエントリは `category_2026-02-01.jsonl` に振り分けられます。

### ネットワークログのフィールド

| フィールド | 説明 |
|------------|------|
| `success` | 許可されたか（allowed と同値） |
| `details.allowed` | 許可されたか（明示的） |
| `details.domain` | 対象ドメイン |
| `details.port` | 対象ポート |
| `rejection_reason` | 拒否理由（拒否時のみ） |

---

## local_pack（非推奨）

`ecosystem/flows/**` に直接配置された Flow/Modifier を仮想 Pack として扱う互換モードです。

### 現在の状態

- **デフォルト**: 無効（`RUMI_LOCAL_PACK_MODE=off`）
- **互換モード**: `RUMI_LOCAL_PACK_MODE=require_approval` で有効化
- **lib 非対応**: local_pack は lib（install/update）をサポートしません

### 廃止計画

local_pack は以下の理由で非推奨です：

1. **セキュリティ**: 承認境界が曖昧になる
2. **一貫性**: 通常の Pack と異なるライフサイクル
3. **保守性**: 特殊ケースによるコード複雑化

**移行手順**:

1. `ecosystem/flows/` 内の Flow/Modifier を Pack 化
2. `ecosystem/packs/{pack_id}/backend/` に配置
3. `ecosystem.json` を作成
4. 承認フローを経て有効化

**廃止スケジュール**:

- v2.0: 警告付きで互換モード維持
- v3.0: 互換モード削除予定

---

## クイックスタート

### 必要条件

- Python 3.9+
- Docker（本番環境）
- Git

### インストール

```bash
git clone https://github.com/your-repo/rumi-ai.git
cd rumi-ai

# セットアップ
python bootstrap.py --cli init

# または
pip install -r requirements.txt
```

### 起動

```bash
# 通常起動
python app.py

# 開発モード（Docker不要）
python app.py --permissive

# ヘッドレスモード
python app.py --headless
```

### Pack承認

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Pack 開発

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

### blocks/hello.py

```python
def run(input_data, context=None):
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

### Flow定義

```yaml
# user_data/shared/flows/hello.flow.yaml
# または ecosystem/packs/my_pack/backend/flows/hello.flow.yaml

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

### 開発の流れ

1. **Pack を作る**: `ecosystem/packs/{pack_id}/backend/` に配置
2. **ecosystem.json を書く**: Pack のメタデータ（pack_id, pack_identity 必須）
3. **blocks/ を書く**: `python_file_call` で呼ばれるコード
4. **Flow を書く**: `user_data/shared/flows/` または Pack 内 `flows/` に配置し、blocks を結線
5. **承認を得る**: ユーザーが Pack を承認
6. **実行**: 承認後、Flow 実行時に blocks が呼ばれる

### 注意事項

- **InterfaceRegistry は内部 API**: Pack から直接 IR を操作しないでください
- **外部通信は Egress Proxy 経由**: `context["http_request"]` を使用
- **lib は Docker 隔離**: `user_data/packs/{pack_id}/` のみ書き込み可能

### 内部ハンドラ一覧

内部実装の参考として、Kernel ハンドラ一覧は [docs/internal_kernel_handlers.md](docs/internal_kernel_handlers.md) を参照してください。Pack 開発では直接使用せず、Flow/Modifier/Blocks を通じて機能を利用してください。

---

## Advanced: vocab/converter

> **注意**: この機能は互換性吸収のための高度な機能です。
> 通常の Pack 開発では使用する必要はありません。

Pack追加だけで互換性を増やせる仕組みです。Flow 内で converter を呼び出すことで、異なるフォーマット間の変換を行えます。

### vocab.txt（同義語グループ）

```
# ecosystem/packs/my_pack/backend/vocab.txt
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

同じ行に書かれた語は同義として扱われます。

### converters（変換器）

```python
# ecosystem/packs/my_pack/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """
    tool形式 → function_calling形式に変換
    """
    # 変換ロジック
    return transformed_data
```

---

## トラブルシューティング

### Docker が利用できない

```
Error: Docker is required but not available
```

開発時は `--permissive` フラグを使用：
```bash
python app.py --permissive
```

または環境変数で設定：
```bash
export RUMI_SECURITY_MODE=permissive
python app.py
```

### Pack が承認されない

```bash
# 承認待ちを確認
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"

# 手動で承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pack が無効化された

ファイル変更でハッシュ不一致になると自動無効化されます：
```bash
# 再承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### ネットワークアクセスが拒否される

```bash
# Grant状態を確認
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"

# 権限を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'
```

### Capability が使えない

capability handler の承認（Trust + copy）後、Grant が必要です：
```bash
# Grant 付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 承認待ち状況の確認

```bash
# summary.json を確認（起動時に自動生成）
cat user_data/pending/summary.json | jq .
```

### 監査ログで原因を調査

```bash
# ネットワーク関連のログ
cat user_data/audit/network_$(date +%Y-%m-%d).jsonl | jq .

# 拒否されたリクエスト
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.success == false)'

# 権限操作のログ
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | jq .

# 共有辞書の操作履歴
cat user_data/settings/shared_dict/journal.jsonl | jq .
```

### 共有辞書で循環が検出された

```
Error: Cycle detected: A -> B creates a loop
```

循環参照は自動的に拒否されます。ジャーナルで履歴を確認：
```bash
cat user_data/settings/shared_dict/journal.jsonl | jq 'select(.result == "cycle_detected")'
```

### pip 依存導入が拒否された

requirements.lock が `NAME==VERSION` 形式に準拠しているか確認してください。URL参照、VCS参照、ローカルパスは禁止されています。

```bash
# pip 申請状況を確認
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 旧ディレクトリの警告

```
WARNING: Using legacy flow path. This is DEPRECATED and will be removed.
```

`flow/` や `ecosystem/flows/` から `flows/`、`user_data/shared/flows/`、または Pack 内 `flows/` へ移行してください。

---

## ライセンス

MIT License
```