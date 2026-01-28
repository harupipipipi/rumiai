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

### 基盤のない基盤

Minecraft の mod は「Minecraft」という基盤を改造します。しかし Rumi AI には改造される「本体」がありません。

```
Minecraft の世界:
┌─────────────────────────────────────┐
│         Minecraft本体                │  ← これを改造
│  (ブロック、クリーパー、etc.)         │
├─────────────────────────────────────┤
│            Mod A / Mod B             │
└─────────────────────────────────────┘

Rumi AI の世界:
┌─────────────────────────────────────┐
│    Component ←→ Component           │
│        ↑           ↓                │  ← 網のように繋がる
│    Component ←→ Component           │
├─────────────────────────────────────┤
│     Kernel (実行ルールのみ)           │  ← 「何を」ではなく「どう動くか」だけ
└─────────────────────────────────────┘
```

### Fail-Soft

エラーが発生してもシステムは停止しません。失敗したコンポーネントは無効化され、診断情報に記録されて継続します。

### USB モデル

各 Pack は互いの存在を知りません。`InterfaceRegistry` という共通バスを通じて疎結合に通信します。

---

## 理想

1. **公式ファイルの編集を必要としない** - 全ては `ecosystem/packs/` 内で完結
2. **診断可能** - 何が起きているか常に見える
3. **セキュリティ** - 承認されていない Pack のコードは実行されない
4. **拡張性** - 誰でも Pack を作成して機能を追加できる
5. **ハードコードしない** - フェーズ名、ファイル名、インターフェース名は全て YAML または Pack が定義

---

## ルール

### Pack のルール

1. **承認必須**: `ecosystem/packs/` に配置された Pack は、ユーザーが承認するまでコードが実行されない
2. **ハッシュ検証**: 承認時に全ファイルの SHA-256 ハッシュを記録。変更があれば再承認が必要
3. **Docker 隔離**: 承認された Pack は Docker コンテナ内で実行される（ホスト OS から隔離）
4. **権限宣言**: Pack は `permissions.json` で必要な権限を宣言する

### 公式コードのルール

1. **ドメイン概念を知らない**: 公式コードに「チャット」「ツール」等の言葉は存在しない
2. **仕組みのみ提供**: 具体的な handler 実装は Pack が提供する
3. **平等**: 公式 Pack という概念は存在しない。全ての Pack は同じルールに従う

---

## ディレクトリ構造

```
project_root/
│
├── app.py                      # Flask エントリポイント
├── bootstrap.py                # セットアップエントリポイント
├── requirements.txt            # Python 依存関係
├── setup.bat                   # Windows セットアップ
├── setup.sh                    # Mac/Linux セットアップ
├── README.md                   # このファイル
│
├── core_runtime/               # カーネル（実行エンジン）
├── backend_core/               # エコシステム基盤
├── docker/                     # Docker 設定（公式）
├── flow/                       # Flow 定義（公式）
├── ecosystem/                  # Pack 格納・統合領域
├── user_data/                  # ユーザーデータ
├── rumi_setup/                 # セットアップシステム
├── bootstrap/                  # ブートストラップスクリプト
├── docs/                       # ドキュメント
└── tests/                      # テスト
```

---

## 各フォルダの説明

### `core_runtime/` - カーネル

**役割**: Flow 駆動の実行エンジン。用途非依存。

| ファイル | 説明 |
|---------|------|
| `kernel.py` | Flow 実行エンジン、Kernel ハンドラ |
| `interface_registry.py` | サービス登録箱（USB バスのような役割） |
| `event_bus.py` | publish/subscribe イベント通信 |
| `diagnostics.py` | 診断情報の集約 |
| `component_lifecycle.py` | コンポーネントのライフサイクル管理 |
| `install_journal.py` | インストール・生成物の追跡 |
| `approval_manager.py` | Pack 承認管理（ハッシュ検証、HMAC 署名） |
| `container_orchestrator.py` | Docker コンテナ管理 |
| `host_privilege_manager.py` | ホスト特権操作管理 |
| `pack_api_server.py` | Pack 管理 HTTP API |
| `permission_manager.py` | 権限管理 |
| `userdata_manager.py` | user_data 安全アクセス層 |
| `function_alias.py` | 関数エイリアス（同義語マッピング） |
| `flow_composer.py` | Flow 合成・修正システム |

**重要な原則**:
- このフォルダのコードは「チャット」「ツール」「AI」等のドメイン概念を知らない
- 提供するのは「仕組み」のみ

---

### `backend_core/ecosystem/` - エコシステム基盤

**役割**: Pack/Component の読み込み、マウント管理。

| ファイル | 説明 |
|---------|------|
| `registry.py` | Pack/Component の読み込みとインデックス |
| `mounts.py` | パス抽象化（マウントポイント管理） |
| `active_ecosystem.py` | アクティブ Pack 管理 |
| `addon_manager.py` | アドオン管理 |
| `compat.py` | 後方互換レイヤー |
| `initializer.py` | エコシステム初期化 |
| `json_patch.py` | RFC 6902 JSON Patch 実装 |
| `uuid_utils.py` | UUID 生成ユーティリティ |
| `spec/` | スキーマ定義とバリデータ |

---

### `docker/` - Docker 設定（公式）

**役割**: コンテナ隔離のための設定とスキーマ。

```
docker/
└── core/                       # 公式設定（編集不可）
    ├── base/
    │   └── Dockerfile          # セキュリティ強化ベースイメージ
    ├── schema/
    │   ├── pack.schema.json    # Pack スキーマ
    │   ├── permission.schema.json
    │   └── grant.schema.json
    ├── runtime/
    │   └── container_agent.py  # コンテナ内エージェント
    └── templates/
        ├── Dockerfile.pack.template
        └── docker-compose.pack.template.yml
```

**重要な原則**:
- 具体的な handler 実装は含まない（Pack が提供）
- スキーマとテンプレートのみ提供

---

### `flow/` - Flow 定義（公式）

**役割**: 起動シーケンスとパイプラインの定義。

```
flow/
├── core/                       # 公式 Flow（編集不可）
│   └── 00_startup.flow.yaml    # セキュリティ対応起動フロー
└── ecosystem/                  # Pack が追加する Flow
    └── .gitkeep
```

**`00_startup.flow.yaml` の内容**:
1. セキュリティ基盤初期化
2. Docker 利用可能性チェック
3. 承認マネージャ初期化
4. Pack 承認状態スキャン
5. コンテナオーケストレータ初期化
6. 承認済み Pack のコンテナ起動
7. コンポーネント検出・ロード

---

### `ecosystem/` - Pack 格納・統合領域

**役割**: Pack の格納と統合設定。

```
ecosystem/
├── packs/                      # Pack 格納先
│   └── {pack_id}/
│       └── backend/
│           ├── ecosystem.json  # Pack メタデータ
│           ├── permissions.json # 権限要求
│           ├── components/     # コンポーネント
│           └── handlers/       # カスタム handler
│
├── flows/                      # 統合 Flow（自動生成）
│   └── {name}.{pack_id}.yaml
│
└── docker/                     # 統合 Docker 設定（自動生成）
    └── {pack_id}/
        ├── handlers/
        ├── scopes/
        ├── grants/
        └── sandbox/
```

**Pack のライフサイクル**:
1. `ecosystem/packs/` に配置
2. システム起動時にスキャン
3. ユーザーが承認
4. ファイルハッシュを記録
5. Docker コンテナで実行

---

### `user_data/` - ユーザーデータ

**役割**: ユーザー固有のデータと設定。

```
user_data/
├── mounts.json                 # マウントポイント設定
├── active_ecosystem.json       # アクティブ Pack 設定
├── permissions/                # 承認状態
│   ├── {pack_id}.grants.json   # Pack 別承認情報
│   └── .secret_key             # HMAC 署名キー
├── flows/                      # ユーザー定義 Flow
├── settings/                   # 設定
├── shared/                     # 共有データ
└── cache/                      # キャッシュ
```

**セキュリティ**:
- `user_data/permissions/*.grants.json` は HMAC 署名で保護
- 改ざんされると Pack が自動的に無効化

---

### `rumi_setup/` - セットアップシステム

**役割**: 初期セットアップとインストールガイド。

```
rumi_setup/
├── cli/                        # CLI インターフェース
├── core/                       # 共通ロジック
│   ├── checker.py              # 環境チェック
│   ├── initializer.py          # 初期化
│   ├── installer.py            # インストール
│   ├── recovery.py             # 復旧
│   └── runner.py               # 実行
├── defaults/                   # デフォルト Pack テンプレート
├── guide/                      # インストールガイド（HTML）
└── web/                        # Web インターフェース
```

---

### `bootstrap/` - ブートストラップ

**役割**: 最初期の環境チェック。

```
bootstrap/
├── README.md
└── 00_env_check.py             # 環境チェックスクリプト
```

---

### `docs/` - ドキュメント

**役割**: 技術ドキュメント。

```
docs/
├── docker_security.txt         # Docker セキュリティ解説
├── ecosystem.md                # エコシステム開発ガイド
└── setup.txt                   # セットアップ詳細
```

---

### `tests/` - テスト

**役割**: 自動テスト。

```
tests/
├── test_ecosystem_phase1.py
├── test_ecosystem_phase2.py
└── ...
```

---

## セキュリティモデル

### 承認フロー

```
Pack 配置 (ecosystem/packs/)
    ↓
メタデータのみ読み込み（コード実行なし）
    ↓
権限・リスク表示
    ↓
ユーザー承認
    ↓
全ファイルの SHA-256 ハッシュを記録
    ↓
初めてコード実行（Docker コンテナ内）
```

### 保護機構

| 機構 | 説明 |
|------|------|
| 承認ゲート | 未承認 Pack のコードは一切実行されない |
| ハッシュ検証 | 承認後にファイルが変更されると無効化 |
| HMAC 署名 | grants.json の改ざんを検出 |
| Docker 隔離 | Pack はコンテナ内で実行、ホスト OS から隔離 |
| 権限宣言 | Pack は必要な権限を明示的に宣言 |

### 脆弱性対策

| 脆弱性 | 対策 |
|--------|------|
| 無条件コード実行 | 承認必須 |
| サンドボックスなし | Docker コンテナ隔離 |
| ファイル改ざん | SHA-256 ハッシュ検証 |
| 設定改ざん | HMAC 署名 |
| 権限昇格 | 明示的な権限付与必須 |

---

## クイックスタート

### 必要条件

- Python 3.9+
- Docker
- Git

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/your-repo/rumi-ai.git
cd rumi-ai

# セットアップを実行
# Windows:
setup.bat

# Mac/Linux:
chmod +x setup.sh
./setup.sh
```

### 起動

```bash
# アプリケーション起動
python app.py
```

ブラウザで `http://localhost:5000` を開きます。

### Pack の承認

```bash
# 承認待ち Pack を確認
curl http://localhost:8765/api/packs/pending

# Pack を承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve
```

---

## API リファレンス

### Pack 管理 API

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `GET` | `/api/packs` | 全 Pack 一覧 |
| `GET` | `/api/packs/pending` | 承認待ち Pack |
| `GET` | `/api/packs/{id}/status` | Pack 状態 |
| `POST` | `/api/packs/scan` | Pack スキャン |
| `POST` | `/api/packs/{id}/approve` | Pack 承認 |
| `POST` | `/api/packs/{id}/reject` | Pack 拒否 |
| `DELETE` | `/api/packs/{id}` | Pack アンインストール |

### Docker API

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `GET` | `/api/docker/status` | Docker 状態 |
| `GET` | `/api/containers` | コンテナ一覧 |
| `POST` | `/api/containers/{id}/start` | コンテナ起動 |
| `POST` | `/api/containers/{id}/stop` | コンテナ停止 |

### 特権 API

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `GET` | `/api/privileges` | 特権一覧 |
| `POST` | `/api/privileges/{pack}/grant/{priv}` | 特権付与 |
| `POST` | `/api/privileges/{pack}/execute/{priv}` | 特権実行 |

---

## Pack 開発

### 最小構成

```
ecosystem/packs/my_pack/
└── backend/
    ├── ecosystem.json
    └── components/
        └── hello/
            ├── manifest.json
            └── setup.py
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

### manifest.json

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

### setup.py

```python
def run(context):
    ir = context["interface_registry"]
    
    def hello_handler(args, ctx):
        name = args.get("name", "World")
        return {"message": f"Hello, {name}!"}
    
    ir.register("service.hello", hello_handler)
```

### 権限要求（permissions.json）

```json
{
  "pack_id": "my_pack",
  "permissions": [
    {
      "type": "userdata.read",
      "paths": ["settings/my_config.json"],
      "reason": "設定を読み込むため"
    }
  ]
}
```

---

## トラブルシューティング

### Docker が利用できない

```
Error: Docker is required but not available
```

Docker Desktop が起動しているか確認してください。

### Pack が承認されない

```bash
# 承認待ちを確認
curl http://localhost:8765/api/packs/pending

# 手動で承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve
```

### Pack が無効化された

ファイルが変更されるとハッシュ不一致で無効化されます。再承認してください。

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve
```

---

## ライセンス

MIT License

---

## コントリビューション

1. **Pack を作る** - 好きな機能を実装
2. **繋がりを作る** - 他の Pack と連携
3. **置き換える** - 既存の機能をより良いもので置換

### ガイドライン

- 公式ファイルの編集は最小限に
- 新機能は `ecosystem/packs/` 内に Pack として実装
- Fail-soft を心がける（エラーでも動き続ける）
- 診断情報を適切に出力する

---

*「基盤がないからこそ、何でも作れる」*
```