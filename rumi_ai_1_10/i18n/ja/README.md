<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# るみAI OS

**「基盤のない基盤」** — 変更する「本体」がないモジュール型 AI フレームワーク

---

## 目的のあるガイド

目的ごとに読み取り先を最初に配置すると、すべてのコードをたどらなくてもエントリ ポイントを見つけることができます。

|やりたいこと |最初に読むところ |どこまで理解できますか |
|---|---|---|
|文書を目的別に追跡したい | [`docs/README.md`](./docs/README.md) | 「やりたいこと→どのドキュメント」を1ページで辿れる |
|まずは始めたい |ルート [`README.md`](../README.md) |最短の起動コマンドとリポジトリの入り口 |
|まずは試してみたい | [`docs/tutorials/runtime-quickstart.md`](./docs/tutorials/runtime-quickstart.md) | `--health`から`/panel/`までの最短チュートリアル |
|コードを読まずに実行時の仕組みを理解したい | [`docs/concepts/system-mechanism.md`](./docs/concepts/system-mechanism.md) |起動、フロー、承認、付与、閲覧者連携の実行パス |
| `rumi_viewer`の起動手順と固まる様子を知りたい | 教えてください。 [`docs/rumi_viewer_start.md`](./docs/rumi_viewer_start.md) | `401`、黒い画面、パネルとdefaultspackの関係 |
| defaultspack のフロントエンドを拡張したい | [`ecosystem/defaultspack/docs/frontend_extensions.md`](./ecosystem/defaultspack/docs/frontend_extensions.md) |右バー、設定、チャット レンダラー、プレビュー フィードを増やす方法 |
|このランタイムのアイデアを知りたい |この README の `Thoughts` |フロー中心、パック前提、フェイルソフトのアイデア |
|ディレクトリの役割を知りたい | `Project structure`の役割 |この README の `core_runtime/`、`ecosystem/`、`user_data/`
|パックの作成/修復 | [`docs/pack-development.md`](../../docs/i18n/ja/pack-development.md) | `ecosystem.json`、`routes.json`、`permissions.json`、シークレットの使用 |
| defaultspackのチャット・AIをフォローしたい | [`ecosystem/defaultspack/README.md`](./ecosystem/defaultspack/README.md) | defaultspack の実装側 |
| defaultspack フロントエンドの今後の取り組みを見てみたいと思います | [`ecosystem/defaultspack/docs/frontend_todo.md`](./ecosystem/defaultspack/docs/frontend_todo.md) |レジストリの進捗状況と次の作業 |
| APIキーとシークレットを設定したい | [`docs/operations.md`](../../docs/i18n/ja/operations.md)の秘密セクション | `user_data/secrets/` と API ルート |
|ビューア経由でブートパスを修正したい | [`../rumi_viewer/src-tauri/src/config.rs`](../rumi_viewer/src-tauri/src/config.rs) および [`../rumi_viewer/src-tauri/src/kernel_manager.rs`](../rumi_viewer/src-tauri/src/kernel_manager.rs) |ビューアはどのカーネルを開始し、どの環境を渡す必要がありますか。
|セットアップパック / 認証を確認したい | [`core_runtime/setup_pack.py`](./core_runtime/setup_pack.py) および [`core_runtime/approval_manager.py`](./core_runtime/approval_manager.py) |セットアップ パックの選択、オール OK 付与、再認証 |
|運用や監査について知りたい | [`docs/operations.md`](../../docs/i18n/ja/operations.md) および [`docs/roadmap.md`](./docs/roadmap.md) |運用API、秘密、今後の方針 |

## 最短のフロアプラン

1. `app.py` によりカーネルが起動します
2. `core_runtime/` には、フロー、パック、承認、および実行インフラストラクチャがあります。
3. `ecosystem/<pack_id>/` は機能本体を提供します
4. `user_data/` には認可状態、シークレット、ストア、監査がある
5. `rumi_viewer/`はカーネルを起動してパネルに接続するシェルになります

## よく利用される出入り口

### 起動確認

```bash
python -m rumi_ai --health
python -m rumi_ai
```

### ビューア開発立ち上げ

```bash
cd ../rumi_viewer/src-tauri
cargo tauri dev
```

### 一般的なテスト

```bash
python -m pytest tests/test_defaultspack_google_provider.py
python -m pytest tests/test_defaultspack_modules.py
```

---

## 感想

### えこひいきはしない

Rumi AI の公式コードは、「チャット」、「ツール」、「プロンプト」、「AI クライアント」、「フロントエンド」などのドメイン概念については何も知りません。これらはすべて、エコシステム内のパックによって定義されます。公式は**実行メカニズム**のみを提供します。

### ファンデーションのないファンデーション

Minecraft Modは『Minecraft』の基盤を改造するものですが、Rumi AIには改造できる「本体」がありません。すべてのアプリケーション機能はパックとして実装され、フローを使用して接続されます。

### フロー中心のアーキテクチャ

フローを使用して、パック間の接続、順序、インストール後の処理を定義します。既存のパックを変更せずに新しい機能を追加できます。

```
          +---------------------------+
          |       Flow Definition     |
          +---------------------------+
                      |
          +---------------------------+
          |    python_file_call       |
          +---------------------------+
            /         |         \
    +--------+  +--------+  +--------+
    | Pack A |  | Pack B |  | Pack C |
    +--------+  +--------+  +--------+
            \         |         /
          +---------------------------+
          |         Kernel            |
          +---------------------------+
```

> **フローインポートソース**: `flows/`、`user_data/shared/flows/`、`ecosystem/<pack_id>/backend/flows/`

### フェイルソフト

エラーが発生してもシステムは停止しません。障害が発生したコンポーネントは無効になり、続行するために診断情報に記録されます。

### 悪意のあるパックに基づくセキュリティ

エコシステムは、サードパーティによって作成される可能性があり、悪意のある作成者が存在する可能性があるという前提で設計されています。

- **承認が必要**: 未承認のパック内のコードは実行されません。
- **ハッシュ検証**: 承認後にファイルが変更された場合は自動的に無効化されます (再承認が必要です)
- **Docker 分離**: 承認されたパックはコンテナー内で実行されます (厳密モード)
- **出力プロキシ**: 外部通信は、UDS ソケットを介したプロキシによってのみ許可されます
- **能力 (Trust + Grant)**: ホストの権限は 2 段階の承認で制御されます

既存の環境で HMAC 署名を使用せずに構成ファイルに再署名するには:

```bash
python -m rumi_ai migrate-hmac
```

---

## プロジェクトの構造

§るみ§0§
<summary>ディレクトリ ツリー (クリックして展開)</summary>

<pre><code>
プロジェクトルート/
§── app.py
§── bootstrap.py
§── 要件.txt
§── 要件-dev.txt
│
§── 流れる/
│ └─ 00_startup.flow.yaml
│
§── core_runtime/
│ §── kernel.py
│ §── kernel_core.py
│ §── kernel_handlers_system.py
│ §── kernel_handlers_runtime.py
│ §── paths.py
│ §── Diagnostics.py
│ §──interface_registry.py
│ §──event_bus.py
│ §── Audit_logger.py
│ §── install_journal.py
│ §──approval_manager.py
│ §── network_grant_manager.py
│ §── egress_proxy.py
│ §── rumi_syscall.py
│ §── syscall.py
│ §──capability_proxy.py
│ §──capability_executor.py
│ §──capability_trust_store.py
│ §──capability_grant_manager.py
│ §──capability_installer.py
│ §── rumi_capability.py
│ §── python_file_executor.py
│ §── secure_executor.py
│ §──container_orchestrator.py
│ §──component_lifecycle.py
│ §── host_privilege_manager.py
│ §── Pack_api_server.py
│ §── flow_loader.py
│ §── flow_modifier.py
│ §── flow_composer.py
│ §── flow_scheduler.py
│ §── function_alias.py
│ §── vocab_registry.py
│ §──shared_dict/
│ │ §── スナップショット.py
│ │ §──journal.py
│ │ └─ リゾルバ.py
│ §── core_pack/
│ │ §── core_store_capability/
│ │ §── core_secrets_capability/
│ │ §── core_flow_capability/
│ │ §── core_communication_capability/
│ │ └─ core_docker_capability/
│ §── function_registry.py
│ §── crypto_utils.py
│ §── lib_executor.py
│ §── pip_installer.py
│ §──pack_importer.py
│ §── Pack_applier.py
│ §── Secrets_store.py
│ §──store_registry.py
│ §──unit_registry.py
│ §──unit_executor.py
│ §──unit_trust_store.py
│ §── hierarchical_grant.py
│ §── lang.py
│ ━──permission_manager.py
│
§── backend_core/
│ └─ 生態系/
│ §── compat.py
│ §── mounts.py
│ §── registry.py
│ §── active_ecosystem.py
│ §── イニシャライザ.py
│ §── uuid_utils.py
│ └─ json_patch.py
│
§── エコシステム/
│ §── <pack_id>/
│ │ └─ バックエンド/
│ │ §── エコシステム.json
│ │ §──permissions.json
│ │ §── 要件.lock
│ │ §── ルート.json
│ │ §── ブロック/
│ │ §── 流れる/
│ │ §── コンポーネント/
│ │ §── lib/
│ │ §── シェア/
│ │ §── vocab.txt
│ │ └─ コンバーター/
│ └─ パック/
│ └─ <pack_id>/...
│
§── user_data/
│ §── 監査/
│ §── 権限/
│ │ §── 承認/
│ │ §── ネットワーク/
│ │ §── 能力/
│ │ └─ .secret_key
│ §── 秘密/
│ §── パック/
│ §── 能力/
│ │ §── ハンドラー/
│ │ §── 信頼/
│ │ └─ お願い/
│ §── ピップ/
│ §──pack_staging/
│ §──pack_backups/
│ §── 共有/
│ │ └─ 流れる/
│ │ └─ 修飾子/
│ §── 保留中/
│ │ └─ 概要.json
│ §── 店舗/
│ └─ 設定/
│ §──shared_dict/
│ └── lib_execution_records.json
│
§── rumi_setup/
│ §── コア/
│ §── cli/
│ §── web/
│ §── ガイド/
│ └── デフォルト/
│
§── lang/
│ §── en.txt
│ └── ja.txt
│
§── テスト/
│ §── test_capability_installer.py
│ §── test_capability_system.py
│ §── test_ecosystem_phase1.py
│ §── test_ecosystem_phase2.py
│ §── test_ecosystem_phase3.py
│ §── test_ecosystem_phase4.py
│ §── test_ecosystem_phase5.py
│ §── test_ecosystem_phase6.py
│ §── test_egress_audit.py
│ §── test_flow_resolution.py
│ §── test_inbox_and_patches.py
│ §── test_pip_installer.py
│ §── test_secure_execution.py
│ └── test_shared_dict.py
│
└── ドキュメント/
    §── アーキテクチャ.md
    §── パック開発.md
    §── オペレーション.md
    ━── ロードマップ.md
</code></pre>

§るみ§0§

### メインディレクトリ

|ディレクトリ |役割 |
|---|---|
| `core_runtime/` |カーネル — フロー実行エンジン、セキュリティ、特権管理 |
| `core_runtime/shared_dict/` |共有辞書システム（スナップショットジャーナル） |
| `core_runtime/core_pack/` |公式機能の実装 (ストア、シークレット、フロー、通信、Docker) |
| `backend_core/ecosystem/` |エコシステムの基盤 — パック/コンポーネントの読み込み/初期化 |
| `ecosystem/` |パックストレージ（外部供給品） |
| `user_data/` |ランタイム永続データ (監査ログ、承認、シークレット、ストア) |
| `rumi_setup/` |セットアップ支援 (CLI / Web / ガイド) |
| `flows/` |公式フロー（起動・拠点） |
| `lang/` |多言語メッセージ |
| `tests/` |テスト |
| `docs/` |ドキュメント |

### メインファイル

|ファイル |役割 |
|---|---|
| `app.py` | OS エントリ ポイント |
| `bootstrap.py` |セットアップ エントリ ポイント |
| `kernel.py` | Mixin アセンブリ/ハンドラーの登録 |
| `kernel_core.py` |フロー実行エンジン本体 |
| `python_file_executor.py` | `python_file_call` 処刑 |
| `secure_executor.py` | Docker分離の実行 |
| `approval_manager.py` |パック承認管理 |
| `capability_proxy.py` |機能プロキシ サーバー (UDS) |
| `egress_proxy.py` |外部通信プロキシ (UDS) |
| `flow_loader.py` |フロー YAML ローダー |
| `flow_modifier.py` |フローモディファイアーアプリケーション |
| `pack_importer.py` |パックインポート（zip/フォルダ→ステージング） |
| `pack_applier.py` |パック適用（ステージング→エコシステム） |

## ビューアグラフエディタ

コントロール パネルの正規のフロントエンド ソースは `../rumi_viewer/frontend` にあります。
`core_runtime/core_pack/core_control_panel/web` には、`/panel/` のカーネルによって提供される、構築された静的アーティファクトが含まれています。

`ecosystem/defaultspack/domain/prompt/`と`ecosystem/defaultspack/blocks/prompt/`には機敏な動作が生きています。ツールの動作は `ecosystem/defaultspack/domain/tool/` と `ecosystem/defaultspack/blocks/tool/` にあります。古いトップレベルの `prompt/`、`tool/`、および `supporter/` インポート シムは削除されました。新しいサポーターのような動作は、defaultspack 関数、エージェント、プロンプト、メモリ、または拡張機能として実装する必要があります。

`../rumi_viewer/frontend/src/pages/Flows.tsx` のグラフ エディターは、パックに特化した固定 UI ではなく、拡張可能なグラフ メタデータを備えたエディターとして扱われます。

- 開始ノードは`rumi_start`です
- ノードは複数のポートを持つことができます
- ポートには複数の`contracts`を保持できます
・`contracts`と一致しないポート同士は接続できません。
- `rumi_graph`をYAMLに保存し、ビューア側で構造を復元する

この設計により、変換専用の特別な機能を追加することなく、パック側で異なる入出力コントラクトを持つノードを定義することで変換の役割を表現できるようになります。

## ベースパック

Rumi AI がグラフファーストの基本起動プロファイルとして `basepack` を選択できるようにするために、`ecosystem/setup_pack/basepack/pack.json` を追加しました。現時点では、既存の `defaultspack` を起動用のシン ブートストラップ プロファイルとして扱い、巨大な重複パックを増やさずに安全に展開しています。

---

## クイックスタート

### 要件

- Python 3.10+
- Docker (本番環境に必要)
- Git

### インストール

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10
python bootstrap.py --cli init
```

### 開始

```bash
# 本番（Docker 必須）
python app.py

# 開発（Docker 不要）
python app.py --permissive
```

### パックの承認

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## ドキュメント

|ドキュメント |目次 |
|---|---|
| [docs/architecture.md](../../docs/i18n/ja/architecture.md) |デザインと機構の全体像 |
| [docs/pack-development.md](../../docs/i18n/ja/pack-development.md) |パック開発ガイド |
| [docs/pack-development-guide.md](../../docs/i18n/ja/pack-development-guide.md) |パック開発のクイック スタート |
| [docs/operations.md](../../docs/i18n/ja/operations.md) |操作ガイド |
| [docs/roadmap.md](./docs/roadmap.md) |ロードマップ |
| [docs/quality_pack/philosophy_memo.md](./docs/quality_pack/philosophy_memo.md) |開発上の意思決定に使用される思考メモ |
| [docs/quality_pack/claude_desktop_quality_pack.md](./docs/quality_pack/claude_desktop_quality_pack.md) |品質保証/監査/回帰検証パック |

---

## ライセンス

MITライセンス
詳細については、リポジトリ ルートの LICENSE を参照してください。
##defaultspack の信頼できる情報源

このリポジトリの正規のdefaultspack実装は次のとおりです。
`ecosystem/defaultspack/`。古い `ecosystem/defaults/` パスと別の
`harupipipipi/rumiai_defaults` リポジトリは互換性ソースまたはスナップショット ソースです。
新しいローカルファーストのランタイム動作は、従来のデフォルトパックに組み込まれる必要があります。
必要に応じてエイリアスを委任して戻します。

defaultspack ランタイムは、クラウド API キーや外部の外部キーなしで起動するように設計されています。
ネットワークアクセス。保証されているデフォルト モデルは `stub/default` です。クラウドプロバイダー
はオプションであり、明示的に選択/構成する必要があります。ローカルファイル、ターミナル、
git ミューテーションはローカル リクエスト ガードで保護され、ワンタイム署名されます。
承認トークン、および編集された監査記録。
