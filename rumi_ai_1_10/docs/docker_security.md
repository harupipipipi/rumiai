

```
================================================================================
Rumi AI - Docker Security System ドキュメント（完全版）
================================================================================

目次
────────────────────────────────────────────────────────────────────────────────
1. 概要
2. アーキテクチャ
3. セキュリティモデル
4. ディレクトリ構造
5. 使用方法
6. 権限システム
7. Flow中心アーキテクチャ
8. python_file_call
9. Egress Proxy
10. lib システム
10.5 lib 隔離実行
11. 監査ログ
12. UDS ソケット権限と --group-add
13. Capability Grant 管理
14. Pending Export
15. トラブルシューティング

================================================================================
1. 概要
================================================================================

Rumi AI Docker Security Systemは、Ecosystem内の各Packを完全に隔離された
環境で実行するセキュリティシステムです。

【設計原則】
- 全てのPackは信頼度ゼロとして扱う（悪意ある作者を想定）
- 承認されていないPackのコードは一切実行されない
- ファイル/ネットワークアクセスは明示的な許可が必要
- 監査ログで全ての操作を記録
- Flow中心：結線・順序・後付け注入をFlowで行い、Pack改造なしに拡張

【セキュリティモード】
- strict（デフォルト、本番推奨）: Docker必須、なければ実行拒否
- permissive（開発用）: Docker不要、警告付きでホスト実行を許可

環境変数で設定:
  RUMI_SECURITY_MODE=strict   # 本番環境
  RUMI_SECURITY_MODE=permissive  # 開発環境

================================================================================
2. アーキテクチャ
================================================================================

┌─────────────────────────────────────────────────────────────────┐
│                         Rumi AI OS                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      Kernel                               │  │
│  │  - Flow実行エンジン                                       │  │
│  │  - python_file_call ハンドラ                             │  │
│  │  - 承認/権限チェック統合                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐     │
│  │ Pack A      │      │ Pack B      │      │ Pack C      │     │
│  │             │      │             │      │             │     │
│  │ blocks/     │      │ blocks/     │      │ blocks/     │     │
│  │ lib/        │      │ lib/        │      │ lib/        │     │
│  │             │      │             │      │             │     │
│  │ 承認必須    │      │ 承認必須    │      │ 承認必須    │     │
│  │ 隔離実行    │      │ 隔離実行    │      │ 隔離実行    │     │
│  └─────────────┘      └─────────────┘      └─────────────┘     │
│         │                    │                    │             │
│         └────────────────────┼────────────────────┘             │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Egress Proxy                            │  │
│  │  - 全外部通信を仲介                                       │  │
│  │  - Pack単位のallowlist制御                               │  │
│  │  - 監査ログ記録                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│                        外部ネットワーク                          │
└─────────────────────────────────────────────────────────────────┘

================================================================================
3. セキュリティモデル
================================================================================

【信頼の境界】

  公式が提供（信頼できる）:
  ├── Kernel（Flow実行エンジン）
  ├── 承認マネージャ（ApprovalManager）
  ├── ネットワーク権限マネージャ（NetworkGrantManager）
  ├── Capability Grant マネージャ（CapabilityGrantManager）
  ├── Egress Proxy
  ├── 監査ログシステム（AuditLogger）
  └── lib実行システム（LibExecutor）

  Packが提供（信頼度ゼロ）:
  ├── Pack のコード（blocks/*.py）
  ├── Pack の lib/（install.py, update.py）
  ├── Pack の Flow定義
  └── Pack の modifier定義

【承認フロー】

  Pack配置 (ecosystem/packs/)
      ↓
  メタデータのみ読み込み（コード実行なし）
      ↓
  ユーザー承認（手動）
      ↓
  全ファイルの SHA-256 ハッシュを記録
      ↓
  初めてコード実行可能に
      ↓
  ファイル変更検出 → 自動的にModified状態 → 再承認必要

【保護機構】

| 機構              | 説明                                         |
|-------------------|----------------------------------------------|
| 承認ゲート        | 未承認 Pack のコードは一切実行されない       |
| ハッシュ検証      | 承認後にファイルが変更されると自動無効化     |
| HMAC 署名         | grants.json の改ざんを検出                   |
| パス制限          | 許可ルート外のファイルアクセスを拒否         |
| ネットワーク制御  | Egress Proxy経由のみ、allowlist制御          |
| UDS ソケット権限  | 0660 + 専用GID で接続可能性を制御            |
| 監査ログ          | 全操作を記録、改ざん検知可能                 |

【Pack状態遷移】

  INSTALLED → (ユーザー承認) → APPROVED → (ファイル変更) → MODIFIED
      ↓                            ↓                           ↓
  (ユーザー拒否)              実行可能                    実行不可
      ↓                                                   ネットワーク不可
  BLOCKED                                                     ↓
                                                    (再承認) → APPROVED

================================================================================
4. ディレクトリ構造
================================================================================

project_root/
├── flows/                          # 公式Flow（起動・基盤）
│   └── 00_startup.flow.yaml
│
├── user_data/
│   ├── shared/
│   │   ├── flows/                  # 共有Flow（外部ツール/packが配置可能）
│   │   │   ├── ai_response.flow.yaml
│   │   │   └── ...
│   │   └── flows/modifiers/        # Flow modifier（差し込み定義）
│   │       ├── tool_inject.modifier.yaml
│   │       └── ...
│   │
│   ├── permissions/
│   │   ├── approvals/              # Pack承認状態
│   │   ├── network/                # Pack単位ネットワーク権限
│   │   │   └── {pack_id}.json
│   │   ├── capabilities/           # Capability Grant（principal単位）
│   │   │   └── {principal_id}.json
│   │   └── .secret_key             # HMAC署名キー
│   │
│   ├── packs/                      # Pack別データディレクトリ（lib RW用）
│   │   └── {pack_id}/
│   │       └── python/             # pip依存 (approve後に生成)
│   │           ├── wheelhouse/
│   │           ├── site-packages/
│   │           └── state.json
│   │
│   ├── pending/                    # Pending Export (起動時に自動生成)
│   │   └── summary.json
│   │
│   ├── audit/                      # 監査ログ
│   │   ├── flow_execution_YYYY-MM-DD.jsonl
│   │   ├── python_file_call_YYYY-MM-DD.jsonl
│   │   ├── network_YYYY-MM-DD.jsonl
│   │   └── ...
│   │
│   ├── settings/
│   │   └── lib_execution_records.json  # lib実行記録
│   │
│   └── ...
│
├── ecosystem/
│   └── packs/                      # Pack格納（旧 ecosystem/<pack_id>/ も可）
│       └── {pack_id}/
│           └── backend/
│               ├── ecosystem.json
│               ├── permissions.json
│               ├── requirements.lock   # pip依存宣言（任意）
│               ├── components/
│               │   └── {component_id}/
│               │       ├── manifest.json
│               │       └── blocks/     # python_file_callで呼ばれるブロック
│               │           ├── generate.py
│               │           └── ...
│               └── lib/                # install/update スクリプト
│                   ├── install.py
│                   └── update.py
│
└── core_runtime/
    ├── kernel.py                   # Flow実行エンジン
    ├── kernel_handlers_runtime.py  # ランタイム系ハンドラ
    ├── flow_loader.py              # Flowファイルローダー
    ├── flow_modifier.py            # Flow modifier適用
    ├── python_file_executor.py     # python_file_call実行
    ├── approval_manager.py         # Pack承認管理
    ├── network_grant_manager.py    # ネットワーク権限管理
    ├── capability_grant_manager.py # Capability Grant管理
    ├── capability_proxy.py         # Capability Proxyサーバー
    ├── egress_proxy.py             # Egress Proxyサーバー
    ├── lib_executor.py             # lib実行管理
    ├── pip_installer.py            # pip依存導入管理
    ├── pack_applier.py             # Pack更新適用
    ├── pack_api_server.py          # HTTP APIサーバー
    ├── secure_executor.py          # セキュア実行層（Docker隔離）
    ├── audit_logger.py             # 監査ログ
    └── ...

【Flow 読み込み元（優先順）】

| 優先度 | パス                                       | 用途                    |
|--------|--------------------------------------------|-------------------------|
| 1      | flows/                                     | 公式Flow（起動・基盤）  |
| 2      | user_data/shared/flows/                    | 共有Flow                |
| 3      | ecosystem/<pack_id>/backend/flows/         | Pack提供のFlow          |
| (deprecated) | ecosystem/flows/                     | local_pack互換（オプトイン、非推奨） |

ecosystem/flows/ は RUMI_LOCAL_PACK_MODE=require_approval でのみ有効。
デフォルトでは無効（off）です。新規Flowは上記1～3に配置してください。

================================================================================
5. 使用方法
================================================================================

【初期セットアップ】

1. 依存関係をインストール:
   pip install -r requirements.txt

2. アプリケーションを起動:
   python app.py

   開発モード（Docker不要）:
   python app.py --permissive

【Pack管理】

全エンドポイントは Authorization: Bearer YOUR_TOKEN が必須です。

# 承認待ちPackを確認
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"

# Packを承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"

# Packを拒否
curl -X POST http://localhost:8765/api/packs/{pack_id}/reject \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "セキュリティ上の懸念"}'

【ネットワーク権限管理】

# ネットワークアクセスを許可
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "my_pack",
    "allowed_domains": ["api.openai.com", "*.anthropic.com"],
    "allowed_ports": [443]
  }'

# ネットワークアクセスを取り消し
curl -X POST http://localhost:8765/api/network/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "reason": "不要になった"}'

# ネットワークGrant一覧
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"

# アクセスチェック
curl -X POST http://localhost:8765/api/network/check \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "domain": "api.openai.com", "port": 443}'

================================================================================
6. 権限システム
================================================================================

【Pack単位Grant】

各Packに対して、以下の権限を個別に付与:

1. 実行権限（承認）
   - ApprovalManagerで管理
   - 承認されていないPackのコードは実行不可
   - ファイル変更でModified状態 → 再承認必要

2. ネットワーク権限
   - NetworkGrantManagerで管理
   - allowed_domains: 許可するドメインリスト
   - allowed_ports: 許可するポートリスト
   - Modified状態で自動無効化

3. Capability Grant
   - CapabilityGrantManagerで管理
   - principal_id × permission_id の組み合わせで管理
   - HMAC署名による改ざん検知
   - 詳細はセクション13を参照

【Grant ファイル形式】

user_data/permissions/network/{pack_id}.json:

{
  "pack_id": "my_pack",
  "enabled": true,
  "allowed_domains": ["api.openai.com", "*.anthropic.com"],
  "allowed_ports": [443, 80],
  "granted_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z",
  "granted_by": "user",
  "notes": "OpenAI/Anthropic APIアクセス用",
  "_hmac_signature": "..."
}

【HMAC署名】

- 全てのgrantファイルはHMAC-SHA256で署名
- 署名キーは user_data/permissions/.secret_key に保存
- 改ざん検出時は該当Packを自動無効化

================================================================================
7. Flow中心アーキテクチャ
================================================================================

【設計思想】

- Flowが中心: Pack間の結線・順序・後付け注入をFlowで行う
- 贔屓なし: 公式は「AI」「tool」「prompt」などのドメイン概念を固定しない
- 既存Pack改造なし: modifierで後から機能を注入

【Flowファイル形式】

flows/*.flow.yaml, user_data/shared/flows/*.flow.yaml,
または ecosystem/<pack_id>/backend/flows/*.flow.yaml:

flow_id: ai_response
inputs:
  user_input: string
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

  - id: generate_response
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      user_input: "${ctx.user_input}"
    output: ai_output

【ステップタイプ】

| タイプ           | 説明                                    |
|------------------|-----------------------------------------|
| handler          | 既存のKernelハンドラを呼び出し          |
| python_file_call | Pythonファイルを実行                    |
| set              | コンテキストに値を設定                  |
| if               | 条件分岐（簡易版）                      |

【実行順序（決定的）】

1. phases の並び順でソート
2. 同じphase内は priority 昇順
3. priorityが同値の場合は id 昇順

================================================================================
8. python_file_call
================================================================================

【概要】

Flowのステップとして任意のPythonファイルを実行する。
入力→出力で次のステップに繋ぐ「Scratchブロック」のような仕組み。

【ステップ定義】

- id: generate_response
  phase: generate
  priority: 50
  type: python_file_call
  owner_pack: ai_client          # 所有Pack（権限判定に使用）
  file: blocks/generate.py       # 実行ファイル（相対パス推奨）
  input:                         # 入力データ（変数展開可能）
    user_input: "${ctx.user_input}"
  output: ai_output              # 出力先コンテキストキー
  timeout_seconds: 60            # タイムアウト（デフォルト60秒）

【Python側の実行契約】

対象ファイルは以下のいずれかの関数を持つこと:

def run(input_data, context):
    """
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
            - http_request: Egress Proxy経由HTTPリクエスト関数

    Returns:
        JSON互換の出力データ
    """
    # 処理
    return {"result": "..."}

# または引数1つ版
def run(input_data):
    return {"result": "..."}

【セキュリティチェック】

実行前に以下をチェック:

1. owner_pack の承認状態（APPROVED以外は拒否）
2. owner_pack のハッシュ検証（Modified検出で拒否）
3. ファイルパスの検証（許可ルート外は拒否）

許可ルート:
- ecosystem/（承認済みPackディレクトリ）
- ecosystem/sandbox/（サンドボックス領域）

【principal_id の扱い (v1)】

v1 では principal_id は常に owner_pack に強制上書きされます。
Flowで principal_id を指定しても、実行時は owner_pack が使用されます。
これは権限の乱用事故を防ぐための措置です。

監査ログには "principal_id_overridden" として警告が記録されます。

将来のバージョンで principal_id の独立運用が検討される場合があります。

【ネットワークアクセス】

python_file_call内から外部通信を行う場合:

def run(input_data, context):
    # 1. アクセス可否をチェック（任意）
    check = context["network_check"]("api.openai.com", 443)
    if not check["allowed"]:
        return {"error": check["reason"]}

    # 2. Egress Proxy経由でリクエスト
    result = context["http_request"](
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        headers={"Authorization": "Bearer ..."},
        body='{"model": "gpt-4", ...}',
        timeout_seconds=30.0
    )

    if not result["success"]:
        return {"error": result["error"]}

    return {"response": result["body"]}

================================================================================
9. Egress Proxy
================================================================================

【概要】

全ての外部ネットワーク通信を仲介するプロキシサーバー。
Pack別UDSソケットでpack_idを確定し（payloadは無視）、
network grant に基づいて allow/deny を判定し、監査ログに記録。

【セキュリティ防御】

- 内部IP禁止（localhost/private/link-local/CGNAT/multicast等）
- DNS rebinding対策（解決結果が内部IPなら拒否）
- リダイレクト上限（3ホップ、各ホップでgrant再チェック）
- リクエスト/レスポンスサイズ制限（1MB / 4MB）
- タイムアウト制限（最大120秒）
- ヘッダー数/サイズ制限
- メソッド制限（GET, HEAD, POST, PUT, DELETE, PATCH）

【UDS ベースの通信】

Pack実行コンテナは --network=none で動作します。
外部通信は UDS ソケット経由でのみ可能です:

  Pack (network=none) → UDS socket → Egress Proxy → 外部API
                                          ↓
                                    network grant確認
                                          ↓
                                      監査ログ記録

Pack別にソケットが作成され、ソケットパスからpack_idが確定されます。
payloadのowner_packフィールドは無視されます（セキュリティ上重要）。

【HTTP API（Pack API Server）】

全エンドポイントは Authorization: Bearer YOUR_TOKEN が必須です。

| メソッド | パス                   | 説明                     |
|----------|------------------------|--------------------------|
| POST     | /api/network/grant     | ネットワーク権限を付与   |
| POST     | /api/network/revoke    | ネットワーク権限を取り消し |
| POST     | /api/network/check     | アクセス可否をチェック   |
| GET      | /api/network/list      | 全Grant一覧              |

【Kernel ハンドラ】

| ハンドラ                    | 説明                     |
|-----------------------------|--------------------------|
| kernel:network.grant        | ネットワーク権限を付与   |
| kernel:network.revoke       | ネットワーク権限を取り消し |
| kernel:network.check        | アクセス可否をチェック   |
| kernel:network.list         | 全Grant一覧              |
| kernel:egress_proxy.start   | プロキシを起動           |
| kernel:egress_proxy.stop    | プロキシを停止           |
| kernel:egress_proxy.status  | プロキシの状態を取得     |

================================================================================
10. lib システム
================================================================================

【概要】

Packの lib/install.py と lib/update.py を管理。
「整理」目的であり、常駐しない。必要時のみ実行。

【実行タイミング】

| 状況                     | 実行されるファイル |
|--------------------------|-------------------|
| 初回導入時               | install.py        |
| ハッシュ変更時           | update.py         |
| それ以外                 | 実行しない        |

【ファイル形式】

lib/install.py:
def run(context):
    """
    Args:
        context:
            - pack_id: Pack ID
            - lib_type: "install"
            - ts: タイムスタンプ
            - lib_dir: libディレクトリパス
            - data_dir: 書き込み可能ディレクトリ（コンテナ内: /data）
    """
    # 初期化処理
    return {"status": "installed"}

lib/update.py:
def run(context):
    """
    Args:
        context:
            - pack_id: Pack ID
            - lib_type: "update"
            - ts: タイムスタンプ
            - lib_dir: libディレクトリパス
            - data_dir: 書き込み可能ディレクトリ（コンテナ内: /data）
    """
    # アップデート処理
    return {"status": "updated"}

【実行記録】

user_data/settings/lib_execution_records.json:
{
  "version": "1.0",
  "updated_at": "2024-01-01T00:00:00Z",
  "records": {
    "my_pack": {
      "pack_id": "my_pack",
      "lib_type": "install",
      "executed_at": "2024-01-01T00:00:00Z",
      "file_hash": "abc123...",
      "success": true,
      "error": null
    }
  }
}

【Kernel ハンドラ】

| ハンドラ                  | 説明                           |
|---------------------------|--------------------------------|
| kernel:lib.process_all    | 全Packのlibを処理              |
| kernel:lib.check          | 実行が必要かチェック           |
| kernel:lib.execute        | 手動実行                       |
| kernel:lib.clear_record   | 実行記録をクリア（再実行強制） |
| kernel:lib.list_records   | 実行記録を一覧                 |

================================================================================
10.5 lib 隔離実行
================================================================================

【概要】

Pack の lib/install.py と lib/update.py は Docker コンテナ内で隔離実行されます。
strictモードでは Docker 必須、permissiveモードでは警告付きでホスト実行を許可。

【コンテナ設定】

lib 実行時の Docker コンテナ設定:

  docker run --rm \
    --name rumi-lib-{pack_id}-{lib_type}-{hash} \
    --network=none \
    --cap-drop=ALL \
    --security-opt=no-new-privileges:true \
    --read-only \
    --tmpfs=/tmp:size=64m,noexec,nosuid \
    --memory=256m \
    --memory-swap=256m \
    --cpus=0.5 \
    --pids-limit=50 \
    --user=65534:65534 \
    --ulimit=nproc=50:50 \
    --ulimit=nofile=100:100 \
    -v {lib_dir}:/lib:ro \
    -v {pack_data_dir}:/data:rw \
    -v {context_file}:/context.json:ro \
    -e RUMI_PACK_ID={pack_id} \
    -e RUMI_LIB_TYPE={lib_type} \
    python:3.11-slim \
    python -c "..."

【マウントポイント】

| パス           | モード | 説明                                    |
|----------------|--------|----------------------------------------|
| /lib           | RO     | lib ディレクトリ（install.py, update.py）|
| /data          | RW     | Pack データディレクトリ（書き込み可能）  |
| /context.json  | RO     | 実行コンテキスト                        |

【RW マウントの制限】

RW マウントは user_data/packs/{pack_id}/ のみに限定されます:

- ホスト側: user_data/packs/{pack_id}/
- コンテナ内: /data

これにより、lib が書き込める範囲を最小限に制限します。

【セキュリティ保証】

| 項目           | 保証                                              |
|----------------|---------------------------------------------------|
| ネットワーク   | --network=none で無効                             |
| ファイルシステム| --read-only でルートFS読み取り専用               |
| 書き込み範囲   | /data（= user_data/packs/{pack_id}/）のみ        |
| 権限昇格       | --cap-drop=ALL, --security-opt=no-new-privileges |
| リソース       | メモリ256MB、CPU 0.5コア、プロセス50個制限       |

【local_pack の扱い】

local_pack（ecosystem/flows/** の仮想Pack）は lib をサポートしません。
lib 実行要求は常にスキップされます。
local_pack 自体が非推奨（deprecated）です。

【context で提供される情報】

lib の run() 関数には以下の context が渡されます:

{
  "pack_id": "my_pack",
  "lib_type": "install",  // または "update"
  "ts": "2024-01-01T00:00:00Z",
  "lib_dir": "/lib",      // コンテナ内のlibディレクトリ
  "data_dir": "/data"     // コンテナ内の書き込み可能ディレクトリ
}

【permissive モードでのホスト実行】

Docker が利用できない場合、permissive モードでは警告付きでホスト実行されます:

- 警告が stderr に出力される
- 監査ログに execution_mode="host_permissive" が記録される
- data_dir にはホスト側の実パス（user_data/packs/{pack_id}/）が渡される

本番環境では必ず strict モードを使用してください。

【監査ログ】

lib 実行は監査ログに記録されます:

{
  "ts": "2024-01-01T00:00:00Z",
  "category": "system",
  "action": "lib_install",
  "success": true,
  "details": {
    "pack_id": "my_pack",
    "lib_type": "install",
    "execution_mode": "container"
  }
}

execution_mode の値:
- "container": Docker コンテナ内で実行
- "host_permissive": permissive モードでホスト実行
- "skipped": local_pack などでスキップ
- "rejected": 承認エラーなどで拒否

================================================================================
11. 監査ログ
================================================================================

【概要】

全ての重要な操作を監査ログに記録。
JSON Lines形式で永続化、カテゴリ別にファイル分割。

【カテゴリ】

| カテゴリ              | 説明                           |
|-----------------------|--------------------------------|
| flow_execution        | Flow実行                       |
| modifier_application  | modifier適用                   |
| python_file_call      | python_file_call実行           |
| approval              | Pack承認操作                   |
| permission            | 権限操作（capability grant含む）|
| network               | ネットワークアクセス           |
| security              | セキュリティイベント           |
| system                | システムイベント               |

【ファイル形式】

user_data/audit/{category}_{date}.jsonl:

ファイル名の日付はエントリの ts から決定されます（深夜跨ぎ対応）。
ts が不正な場合は書き込み時点の日付にフォールバックします。

{"ts":"2024-01-01T00:00:00Z","category":"python_file_call","severity":"info",
 "action":"execute_python_file","success":true,"flow_id":"ai_response",
 "step_id":"generate","phase":"generate","owner_pack":"ai_client",
 "execution_mode":"host_permissive","details":{"file":"blocks/generate.py",
 "execution_time_ms":123.45}}

【エントリ構造】

{
  "ts": "ISO8601タイムスタンプ",
  "category": "カテゴリ",
  "severity": "info|warning|error|critical",
  "action": "アクション名",
  "success": true/false,
  "flow_id": "Flow ID（該当する場合）",
  "step_id": "ステップID（該当する場合）",
  "phase": "フェーズ名（該当する場合）",
  "owner_pack": "Pack ID（該当する場合）",
  "execution_mode": "実行モード（該当する場合）",
  "error": "エラーメッセージ（失敗時）",
  "error_type": "エラータイプ（失敗時）",
  "rejection_reason": "拒否理由（拒否時）",
  "details": { ... }
}

【ネットワークログのフィールド】

| フィールド             | 説明                             |
|------------------------|----------------------------------|
| success                | 許可されたか（allowed と同値）   |
| details.allowed        | 許可されたか（明示的）           |
| details.domain         | 対象ドメイン                     |
| details.port           | 対象ポート                       |
| rejection_reason       | 拒否理由（拒否時のみ）           |

【Kernel ハンドラ】

| ハンドラ               | 説明                 |
|------------------------|----------------------|
| kernel:audit.query     | ログを検索           |
| kernel:audit.summary   | サマリーを取得       |
| kernel:audit.flush     | バッファをフラッシュ |

【クエリ例】

# 特定Packの失敗ログを検索
result = kernel.execute_flow_sync("_internal", {
    "handler": "kernel:audit.query",
    "args": {
        "category": "python_file_call",
        "pack_id": "my_pack",
        "success_only": False,
        "limit": 100
    }
})

================================================================================
12. UDS ソケット権限と --group-add
================================================================================

【概要】

strict モードでは、Pack 実行コンテナは --user=65534:65534 (nobody) で
動作します。UDS ソケットがデフォルトの 0660 (root:root) のままだと、
コンテナからソケットに接続できません。

専用 GID を設定することで、0660 を維持しつつ安全に接続を可能にします。

【設定手順】

1. 専用 GID を決定（例: 1099）

2. 環境変数を設定:
   # Egress Proxy ソケット用
   export RUMI_EGRESS_SOCKET_GID=1099

   # Capability Proxy ソケット用
   export RUMI_CAPABILITY_SOCKET_GID=1099

3. ソケット作成時の動作:
   - ソケットファイルが chmod 0660 で作成される
   - 指定された GID で chown される（best-effort）
   - ベースディレクトリは chmod 0750 で保護される

4. docker run 時の動作:
   - --group-add=1099 が自動的に付与される
   - コンテナ内ユーザー (nobody:65534) がソケットのグループに所属
   - ソケットへの接続が可能になる

【環境変数一覧】

| 環境変数                        | 説明                              | デフォルト |
|---------------------------------|-----------------------------------|-----------|
| RUMI_EGRESS_SOCKET_GID          | Egress ソケットのGID              | なし      |
| RUMI_CAPABILITY_SOCKET_GID      | Capability ソケットのGID          | なし      |
| RUMI_EGRESS_SOCKET_MODE         | Egress ソケットのパーミッション   | 0660      |
| RUMI_CAPABILITY_SOCKET_MODE     | Capability ソケットのパーミッション | 0660    |
| RUMI_EGRESS_SOCK_DIR            | Egress ソケットのベースディレクトリ | /run/rumi/egress/packs |
| RUMI_CAPABILITY_SOCK_DIR        | Capability ソケットのベースディレクトリ | /run/rumi/capability/principals |

【GID 未設定の場合の動作】

- ソケットは root:root で 0660 になりうる
- コンテナ (nobody:65534) からアクセスできない
- --group-add は付与されない

【0666 緩和モード（非推奨）】

最終手段として、ソケットを 0666 に緩和できます:

  export RUMI_EGRESS_SOCKET_MODE=0666
  export RUMI_CAPABILITY_SOCKET_MODE=0666

この場合:
- 任意のユーザーがソケットに接続可能になる
- 監査ログに SECURITY WARNING が記録される
- 本番環境では非推奨

【--group-add の適用条件】

docker run に --group-add が付与されるのは以下の条件を全て満たす場合:

1. 対応する GID 環境変数が設定されている（正の整数）
2. 対応するソケットがコンテナにマウントされる

つまり:
- Egress ソケットをマウントする場合のみ RUMI_EGRESS_SOCKET_GID の group-add
- Capability ソケットをマウントする場合のみ RUMI_CAPABILITY_SOCKET_GID の group-add
- 両方マウントする場合は両方の GID が追加（重複する場合は1つ）

【fail-soft 動作】

- GID 値が不正（空文字列、負数、int変換不可）の場合: 警告のみ、group-add なし
- chown 失敗の場合: 監査ログに警告、処理は続行
- chmod 失敗の場合: 監査ログに警告、処理は続行

================================================================================
13. Capability Grant 管理
================================================================================

【概要】

Capability システムは Trust と Grant の二段構えで動作します:

- Trust: handler_id + sha256 の allowlist。handler.py の内容が信頼済みか判定
- Grant: principal_id × permission_id の権限付与。誰がどの capability を使えるか管理

capability handler を approve（Trust登録 + コピー）した後、実際に使用するには
Grant の付与が必要です。公式は permission_id の意味を解釈しません（No Favoritism）。

【Kernel ハンドラ】

| ハンドラ                    | 説明                           |
|-----------------------------|--------------------------------|
| kernel:capability.grant     | Capability Grant を付与        |
| kernel:capability.revoke    | Capability Grant を取り消し    |
| kernel:capability.list      | Capability Grant を一覧        |

使用例:

# Grant 付与
- type: handler
  input:
    handler: "kernel:capability.grant"
    args:
      principal_id: "my_pack"
      permission_id: "fs.read"
      config:
        allowed_paths: ["/data"]

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

【HTTP API（Pack API Server）】

全エンドポイントは Authorization: Bearer YOUR_TOKEN が必須です。

| メソッド | パス                                     | 説明                 |
|----------|------------------------------------------|----------------------|
| POST     | /api/capability/grants/grant             | Grantを付与          |
| POST     | /api/capability/grants/revoke            | Grantを取り消し      |
| GET      | /api/capability/grants?principal_id=xxx  | Grant一覧            |

使用例:

# Grant 付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "my_pack",
    "permission_id": "fs.read",
    "config": {"allowed_paths": ["/data"]}
  }'

# Grant 一覧
curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Grant 取り消し
curl -X POST http://localhost:8765/api/capability/grants/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'

【監査ログ】

Grant 操作は permission カテゴリに記録されます:

{
  "ts": "2024-01-01T00:00:00Z",
  "category": "permission",
  "severity": "info",
  "action": "permission_grant",
  "success": true,
  "owner_pack": "my_pack",
  "details": {
    "permission_type": "capability_grant",
    "principal_id": "my_pack",
    "permission_id": "fs.read",
    "has_config": true,
    "source": "api"
  }
}

【HMAC 改ざん検知】

CapabilityGrantManager は全ての grant ファイルに HMAC-SHA256 署名を付与します。
ファイルが外部から改ざんされた場合、読み込み時に検知され無効化されます。

================================================================================
14. Pending Export
================================================================================

【概要】

起動時に承認待ち状況を user_data/pending/summary.json に自動書き出しします。
外部ツール（UI、CLI等）はこのファイルを読むだけで現在の状況を把握できます。

公式はこの出力の消費者を知りません（No Favoritism）。
誰でも読める中立な出力として扱われます。

【生成タイミング】

公式起動Flow（flows/00_startup.flow.yaml）の ecosystem フェーズで
kernel:pending.export ハンドラが実行されます。

fail_soft: true のため、生成に失敗しても起動は止まりません。

【出力形式】

user_data/pending/summary.json:

{
  "ts": "2026-02-11T15:00:00Z",
  "version": "1.0",
  "packs": {
    "pending_count": 2,
    "pending_ids": ["pack_a", "pack_b"],
    "modified_count": 1,
    "modified_ids": ["pack_c"],
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

【fail-soft 動作】

各モジュール（ApprovalManager、CapabilityInstaller、PipInstaller）が
import できない場合、そのセクションには "error" キーが含まれます:

{
  "packs": {"error": "ApprovalManager not available"},
  "capability": {"pending_count": 1, ...},
  "pip": {"error": "PipInstaller not available"}
}

取れた範囲だけが書き出されます。

【Kernel ハンドラ】

| ハンドラ               | 説明                                     |
|------------------------|------------------------------------------|
| kernel:pending.export  | summary.json を生成                      |

================================================================================
15. トラブルシューティング
================================================================================

【python_file_call が実行されない】

1. Pack が承認されているか確認:
   curl http://localhost:8765/api/packs/{pack_id}/status \
     -H "Authorization: Bearer YOUR_TOKEN"

2. ファイルが存在するか確認:
   ls ecosystem/packs/{pack_id}/backend/blocks/
   # または
   ls ecosystem/{pack_id}/backend/blocks/

3. 監査ログで拒否理由を確認:
   cat user_data/audit/python_file_call_$(date +%Y-%m-%d).jsonl | \
     jq 'select(.success == false)'

【ネットワークアクセスが拒否される】

1. ネットワーク権限を確認:
   curl http://localhost:8765/api/network/list \
     -H "Authorization: Bearer YOUR_TOKEN"

2. 許可するドメイン/ポートを追加:
   curl -X POST http://localhost:8765/api/network/grant \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"pack_id": "...", "allowed_domains": ["..."], "allowed_ports": [443]}'

3. PackがModified状態でないか確認:
   curl http://localhost:8765/api/packs/{pack_id}/status \
     -H "Authorization: Bearer YOUR_TOKEN"

【UDS ソケットに接続できない (strict モード)】

1. GID が設定されているか確認:
   echo $RUMI_EGRESS_SOCKET_GID
   echo $RUMI_CAPABILITY_SOCKET_GID

2. ソケットのパーミッションを確認:
   ls -la /run/rumi/egress/packs/
   ls -la /run/rumi/capability/principals/

3. docker run に --group-add が付いているか確認:
   # 監査ログまたは diagnostics の warnings に
   # "Docker --group-add applied: [1099]" と記録されます

4. 応急処置（非推奨）:
   export RUMI_EGRESS_SOCKET_MODE=0666
   export RUMI_CAPABILITY_SOCKET_MODE=0666

【Pack が Modified になった】

ファイルが変更されるとModified状態になり、実行・ネットワークが無効化されます。

再承認する:
   curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
     -H "Authorization: Bearer YOUR_TOKEN"

【Capability Grant が効かない】

1. handler が approve（Trust登録 + コピー）されているか確認:
   curl "http://localhost:8765/api/capability/requests?status=installed" \
     -H "Authorization: Bearer YOUR_TOKEN"

2. Grant が付与されているか確認:
   curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
     -H "Authorization: Bearer YOUR_TOKEN"

3. Grant を付与:
   curl -X POST http://localhost:8765/api/capability/grants/grant \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'

【lib が実行されない】

1. 実行記録を確認:
   cat user_data/settings/lib_execution_records.json

2. 記録をクリアして再実行を強制:
   # kernel:lib.clear_record を呼び出し

3. 手動実行:
   # kernel:lib.execute を呼び出し

4. Docker が利用可能か確認（strictモード）:
   docker info

5. 監査ログを確認:
   cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | \
     jq 'select(.action | contains("lib"))'

【lib の書き込みが失敗する】

lib は /data（= user_data/packs/{pack_id}/）にのみ書き込み可能です。
それ以外のパスへの書き込みは --read-only により失敗します。

context["data_dir"] を使用して書き込み先を指定してください:

def run(context):
    data_dir = context.get("data_dir", "/data")
    # data_dir 内に書き込む
    with open(f"{data_dir}/config.json", "w") as f:
        f.write("{}")

【pip 依存のインストールが拒否される】

1. Pack が承認済みか確認（strict モードでは必須）:
   curl http://localhost:8765/api/packs/{pack_id}/status \
     -H "Authorization: Bearer YOUR_TOKEN"

2. requirements.lock の形式を確認:
   - NAME==VERSION 行のみ許可
   - URL, VCS, ローカルパス, pipオプション, @ direct ref は禁止

3. pip requests の状態を確認:
   curl "http://localhost:8765/api/pip/requests?status=all" \
     -H "Authorization: Bearer YOUR_TOKEN"

4. blocked されている場合は unblock:
   curl -X POST "http://localhost:8765/api/pip/blocked/{key}/unblock" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Re-evaluation"}'

【Egress Proxy が起動しない】

1. ポート競合を確認:
   lsof -i :8766

2. 別ポートで起動:
   # kernel:egress_proxy.start に port 引数を指定

【pending summary.json が生成されない】

1. user_data/pending/ ディレクトリの書き込み権限を確認

2. 起動ログで pending_export ステップの結果を確認

3. fail_soft: true のためエラーでも起動は止まりませんが、
   diagnostics にエラーが記録されます

【監査ログの確認方法】

# 今日のログを確認
ls -la user_data/audit/

# 特定カテゴリのログを確認
cat user_data/audit/network_$(date +%Y-%m-%d).jsonl | jq .

# 失敗のみ抽出
cat user_data/audit/python_file_call_$(date +%Y-%m-%d).jsonl | \
  jq 'select(.success == false)'

# lib 実行ログを確認
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | \
  jq 'select(.action | contains("lib"))'

# capability grant 操作を確認
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | \
  jq 'select(.details.permission_type == "capability_grant")'

# principal_id 上書き警告を確認
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | \
  jq 'select(.action == "principal_id_overridden")'

【開発モードでの注意】

RUMI_SECURITY_MODE=permissive で実行すると:
- Docker なしでもコード実行可能
- 警告が毎回表示される
- 監査ログに "host_permissive" と記録される
- pip 依存の承認チェックで ApprovalManager 不在でも許可される

本番環境では必ず strict モードを使用してください。

================================================================================
                              ドキュメント終わり
================================================================================
```