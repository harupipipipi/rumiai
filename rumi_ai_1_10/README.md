

```markdown
# Rumi AI OS

**「基盤のない基盤」** — 改造される「本体」が存在しないモジュラーAIフレームワーク

---

## 思想

### 贔屓なし（No Favoritism）

Rumi AI の公式コードは「チャット」「ツール」「プロンプト」「AIクライアント」「フロントエンド」といったドメイン概念を**一切知りません**。これらは全て ecosystem 内の Pack が定義します。公式が提供するのは**実行の仕組み**だけです。

### 基盤のない基盤

Minecraft の mod は「Minecraft」という基盤を改造します。しかし Rumi AI には改造される「本体」がありません。全てのアプリケーション機能は Pack として実装され、Flow で結線されます。

### Flow 中心アーキテクチャ

Pack 間の結線・順序・後付け注入を Flow で定義します。既存 Pack の改造なしに新機能を追加できます。

```
┌─────────────────────────────────────────────────────────────┐
│                        Flow 定義                             │
│  (flows/, user_data/shared/flows/,                          │
│   ecosystem/<pack_id>/backend/flows/)                       │
├─────────────────────────────────────────────────────────────┤
│                     python_file_call                         │
│              (Pack 内のブロックを実行)                        │
├─────────────────────────────────────────────────────────────┤
│    Pack A         Pack B         Pack C                      │
│   (blocks/)      (blocks/)      (blocks/)                    │
├─────────────────────────────────────────────────────────────┤
│                      Kernel                                  │
│            (実行エンジン・セキュリティ)                       │
└─────────────────────────────────────────────────────────────┘
```

### Fail-Soft

エラーが発生してもシステムは停止しません。失敗したコンポーネントは無効化され、診断情報に記録されて継続します。

### 悪意 Pack 前提のセキュリティ

ecosystem は第三者が作成でき、悪意ある作者も存在しうるという前提で設計されています。

- **承認必須**: 未承認 Pack のコードは一切実行されない
- **ハッシュ検証**: 承認後にファイルが変更されると自動無効化（再承認必要）
- **Docker 隔離**: 承認済み Pack はコンテナ内で実行（strict モード）
- **Egress Proxy**: 外部通信は UDS ソケット経由のプロキシでのみ許可
- **Capability（Trust + Grant）**: ホスト権限は二段階の承認で制御

---

## プロジェクト構造

```
project_root/
├── app.py                          # OS エントリポイント
├── bootstrap.py                    # セットアップエントリポイント
├── requirements.txt                # Python 依存関係
├── requirements-dev.txt            # 開発用依存関係
│
├── flows/                          # 公式 Flow（起動・基盤）
│   └── 00_startup.flow.yaml
│
├── core_runtime/                   # カーネル（実行エンジン）
│   ├── kernel.py                   # Mixin 組み立て・ハンドラ登録
│   ├── kernel_core.py              # Flow 実行エンジン本体
│   ├── kernel_handlers_system.py   # 起動/システム系ハンドラ
│   ├── kernel_handlers_runtime.py  # 運用/実行系ハンドラ
│   │
│   ├── paths.py                    # パス解決・Pack 探索
│   ├── diagnostics.py              # 診断情報
│   ├── interface_registry.py       # 内部サービス登録
│   ├── event_bus.py                # イベント通信
│   ├── audit_logger.py             # 監査ログ
│   ├── install_journal.py          # インストールジャーナル
│   │
│   ├── approval_manager.py         # Pack 承認管理
│   ├── network_grant_manager.py    # ネットワーク権限管理
│   ├── egress_proxy.py             # 外部通信プロキシ（UDS）
│   ├── rumi_syscall.py             # コンテナ内 syscall API
│   ├── syscall.py                  # syscall 実装
│   │
│   ├── capability_proxy.py         # Capability Proxy サーバー（UDS）
│   ├── capability_executor.py      # Capability 実行
│   ├── capability_handler_registry.py # Handler レジストリ
│   ├── capability_trust_store.py   # Trust Store（sha256 allowlist）
│   ├── capability_grant_manager.py # Grant 管理（principal × permission）
│   ├── capability_installer.py     # Handler 候補導入
│   ├── rumi_capability.py          # コンテナ内 capability API
│   │
│   ├── python_file_executor.py     # python_file_call 実行
│   ├── secure_executor.py          # Docker 隔離実行
│   ├── container_orchestrator.py   # コンテナ管理
│   ├── component_lifecycle.py      # Component ライフサイクル管理
│   ├── host_privilege_manager.py   # ホスト権限管理
│   ├── pack_api_server.py          # HTTP API サーバー
│   │
│   ├── flow_loader.py              # Flow YAML ローダー
│   ├── flow_modifier.py            # Flow modifier 適用
│   ├── flow_composer.py            # Flow 合成
│   ├── function_alias.py           # 関数エイリアス
│   ├── vocab_registry.py           # 語彙レジストリ
│   ├── shared_dict/                # 共有辞書システム
│   │   ├── snapshot.py
│   │   ├── journal.py
│   │   └── resolver.py
│   │
│   ├── lib_executor.py             # lib install/update 実行
│   ├── pip_installer.py            # pip 依存ライブラリ導入
│   │
│   ├── pack_importer.py            # Pack import（zip/folder → staging）
│   ├── pack_applier.py             # Pack apply（staging → ecosystem）
│   │
│   ├── secrets_store.py            # Secrets 管理
│   ├── store_registry.py           # Store レジストリ
│   ├── unit_registry.py            # Unit レジストリ
│   ├── unit_executor.py            # Unit 実行
│   ├── unit_trust_store.py         # Unit Trust Store
│   ├── hierarchical_grant.py       # 階層権限（parent > child）
│   │
│   ├── lang.py                     # 多言語ユーティリティ
│   └── permission_manager.py       # 権限管理
│
├── backend_core/                   # エコシステム基盤
│   └── ecosystem/
│       ├── compat.py               # 互換性ユーティリティ
│       ├── mounts.py               # パス抽象化
│       ├── registry.py             # Pack/Component 読み込み
│       ├── active_ecosystem.py     # アクティブ ecosystem 管理
│       ├── initializer.py          # 初期化
│       ├── uuid_utils.py           # UUID ユーティリティ
│       ├── json_patch.py           # JSON Patch
│       └── addon_manager.py        # Addon 管理（deprecated）
│
├── ecosystem/                      # Pack 格納（外部供給物）
│   ├── <pack_id>/                  # 推奨パス
│   │   └── backend/
│   │       ├── ecosystem.json
│   │       ├── permissions.json
│   │       ├── requirements.lock
│   │       ├── blocks/
│   │       ├── flows/
│   │       ├── components/
│   │       ├── lib/
│   │       ├── share/
│   │       ├── vocab.txt
│   │       └── converters/
│   └── packs/                      # 互換パス（legacy）
│       └── <pack_id>/...
│
├── user_data/                      # 実行時永続データ
│   ├── audit/                      # 監査ログ
│   ├── permissions/                # 承認・権限
│   │   ├── approvals/
│   │   ├── network/
│   │   ├── capabilities/
│   │   └── .secret_key
│   ├── secrets/                    # Secrets（1 key = 1 file）
│   ├── packs/                      # Pack 別データ（lib RW, pip 依存）
│   ├── capabilities/               # Capability handler・Trust・申請
│   │   ├── handlers/
│   │   ├── trust/
│   │   └── requests/
│   ├── pip/                        # pip 候補申請・履歴
│   ├── pack_staging/               # Pack import staging
│   ├── pack_backups/               # Pack apply バックアップ
│   ├── shared/                     # 共有 Flow・Modifier
│   │   └── flows/
│   │       └── modifiers/
│   ├── pending/                    # 承認待ちサマリー
│   │   └── summary.json
│   └── settings/                   # 設定・共有辞書
│       ├── shared_dict/
│       └── lib_execution_records.json
│
├── rumi_setup/                     # セットアップ支援
│   ├── core/                       # 共通ロジック
│   ├── cli/                        # CLI インターフェース
│   ├── web/                        # Web インターフェース
│   ├── guide/                      # インストールガイド（HTML）
│   └── defaults/                   # default Pack テンプレート
│
├── lang/                           # 多言語メッセージ
│   ├── en.txt
│   └── ja.txt
│
├── tests/                          # テスト
│   ├── test_capability_installer.py
│   ├── test_capability_system.py
│   ├── test_ecosystem_phase1.py
│   ├── test_ecosystem_phase2.py
│   ├── test_ecosystem_phase3.py
│   ├── test_ecosystem_phase4.py
│   ├── test_ecosystem_phase5.py
│   ├── test_ecosystem_phase6.py
│   ├── test_egress_audit.py
│   ├── test_flow_resolution.py
│   ├── test_inbox_and_patches.py
│   ├── test_pip_installer.py
│   ├── test_secure_execution.py
│   └── test_shared_dict.py
│
└── docs/
    ├── architecture.md             # 設計と仕組みの全体像
    ├── pack-development.md         # Pack 開発ガイド
    ├── operations.md               # 運用ガイド
    └── roadmap.md                  # ロードマップ
```

---

## クイックスタート

### 必要条件

- Python 3.9+
- Docker（本番環境で必須）
- Git

### インストール

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumi-ai
python bootstrap.py --cli init
```

### 起動

```bash
# 本番（Docker 必須）
python app.py

# 開発（Docker 不要）
python app.py --permissive
```

### Pack 承認

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [docs/architecture.md](docs/architecture.md) | 設計と仕組みの全体像（Flow、セキュリティ、権限、監査） |
| [docs/pack-development.md](docs/pack-development.md) | Pack 開発ガイド（ブロック、Flow、Modifier、lib、pip 依存） |
| [docs/operations.md](docs/operations.md) | 運用ガイド（HTTP API、承認ワークフロー、セットアップ、トラブルシューティング） |
| [docs/roadmap.md](docs/roadmap.md) | ロードマップ（設計思想、過去案、将来計画） |

---

## ライセンス

MIT License
```