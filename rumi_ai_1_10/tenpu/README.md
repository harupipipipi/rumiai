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
│  (flows/, ecosystem/flows/, ecosystem/flows/modifiers/)     │
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
│   ├── lib_executor.py         # lib install/update実行
│   ├── audit_logger.py         # 監査ログ
│   ├── interface_registry.py   # 内部サービス登録（Pack非公開）
│   ├── event_bus.py            # イベント通信
│   ├── diagnostics.py          # 診断情報
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
├── ecosystem/
│   ├── flows/                  # エコシステムFlow
│   │   ├── *.flow.yaml
│   │   └── modifiers/          # Flow modifier
│   │       └── *.modifier.yaml
│   │
│   └── packs/                  # Pack格納
│       └── {pack_id}/
│           └── backend/
│               ├── ecosystem.json
│               ├── blocks/     # python_file_callブロック
│               ├── lib/        # install.py, update.py
│               ├── vocab.txt   # 同義語グループ（任意）
│               └── converters/ # 変換器（任意）
│
├── user_data/
│   ├── permissions/
│   │   ├── approvals/          # Pack承認状態
│   │   ├── network/            # ネットワーク権限
│   │   └── .secret_key
│   ├── audit/                  # 監査ログ
│   ├── settings/
│   │   └── shared_dict/        # 共有辞書データ
│   │       ├── snapshot.json
│   │       └── journal.jsonl
│   └── ...
│
├── flow/                       # [DEPRECATED] 旧Flowディレクトリ
│   ├── core/                   # → flows/ へ移行してください
│   └── ecosystem/              # → ecosystem/flows/ へ移行してください
│
└── docs/
    └── internal_kernel_handlers.md  # 内部ハンドラ一覧
```

**注意**: `flow/` ディレクトリは非推奨です。新規Flowは `flows/` または `ecosystem/flows/` に配置してください。

---

## Flow システム

### Flow ファイル形式

```yaml
# ecosystem/flows/ai_response.flow.yaml

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
# ecosystem/flows/modifiers/tool_inject.modifier.yaml

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

```python
# Grant設定
kernel.execute("kernel:network.grant", {
    "pack_id": "my_pack",
    "allowed_domains": ["api.example.com", "*.openai.com"],
    "allowed_ports": [443]
})
```

### Egress Proxy

Packは直接外部通信できません。全ての通信はEgress Proxyを経由します：

```
Pack (network=none) → Egress Proxy → 外部API
                          ↓
                    network grant確認
                          ↓
                      監査ログ記録
```

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

**セキュリティ**: lib は Docker コンテナ内で隔離実行されます（strictモード）。
RW マウントは `user_data/packs/{pack_id}/` のみに限定されます。

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

## 監査ログ

全ての重要な操作が `user_data/audit/` に記録されます。

### カテゴリ

| カテゴリ | 内容 |
|----------|------|
| `flow_execution` | Flow実行 |
| `modifier_application` | modifier適用 |
| `python_file_call` | ブロック実行 |
| `approval` | Pack承認操作 |
| `permission` | 権限操作 |
| `network` | ネットワーク通信 |
| `security` | セキュリティイベント |
| `system` | システムイベント |

### ネットワークログのフィールド

ネットワーク関連のログには以下のフィールドが含まれます：

| フィールド | 説明 |
|------------|------|
| `success` | 許可されたか（allowed と同値） |
| `details.allowed` | 許可されたか（明示的） |
| `details.domain` | 対象ドメイン |
| `details.port` | 対象ポート |
| `rejection_reason` | 拒否理由（拒否時のみ） |

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
# API経由
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer {token}"
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

### 開発の流れ

1. **Pack を作る**: `ecosystem/packs/{pack_id}/backend/` に配置
2. **ecosystem.json を書く**: Pack のメタデータ
3. **blocks/ を書く**: `python_file_call` で呼ばれるコード
4. **Flow を書く**: `ecosystem/flows/` に配置し、blocks を結線
5. **承認を得る**: ユーザーが Pack を承認
6. **実行**: 承認後、Flow 実行時に blocks が呼ばれる

### 注意事項

- **InterfaceRegistry は内部 API**: Pack から直接 IR を操作しないでください
- **外部通信は Egress Proxy 経由**: `context["http_request"]` を使用
- **lib は Docker 隔離**: `user_data/packs/{pack_id}/` のみ書き込み可能

### 内部ハンドラ一覧

内部実装の参考として、Kernel ハンドラ一覧は [docs/internal_kernel_handlers.md](docs/internal_kernel_handlers.md) を参照してください。
Pack 開発では直接使用せず、Flow/Modifier/Blocks を通じて機能を利用してください。

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

詳細は `docs/advanced_vocab.md`（準備中）を参照してください。

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
curl http://localhost:8765/api/packs/pending

# 手動で承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve
```

### Pack が無効化された

ファイル変更でハッシュ不一致になると自動無効化されます：
```bash
# 再承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve
```

### ネットワークアクセスが拒否される

```bash
# Grant状態を確認
curl http://localhost:8765/api/network/list

# 権限を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'
```

### 監査ログで原因を調査

```bash
# ネットワーク関連のログ
cat user_data/audit/network_$(date +%Y-%m-%d).jsonl | jq .

# 拒否されたリクエスト
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.success == false)'

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

### 旧flowディレクトリの警告

```
WARNING: Using legacy flow path (flow/). This is DEPRECATED and will be removed.
```

`flow/` から `flows/` または `ecosystem/flows/` へ移行してください。

---

## ライセンス

MIT License
```