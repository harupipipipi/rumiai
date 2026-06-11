<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# ルミアイ

Rumi AI は、モジュール式の AI ランタイムおよびツール ワークスペースです。

リポジトリはランタイム実装を `rumi_ai_1_10/` に保持し、`rumi_ai/` はバージョン安定した Python エントリポイントを提供します。正規のコントロール パネル フロントエンド ソースは `rumi_viewer/frontend` にあります。カーネルは、その構築されたアーティファクトを `/panel/` で提供します。

## こんなときに読んでください...

|やりたいこと |最初に読むところ |サプリメント |
|---|---|---|
|目的別にドキュメントをフォローしたい | [`rumi_ai_1_10/docs/README.md`](./rumi_ai_1_10/docs/README.md) | 「やりたいこと」から読む順番にご案内します |
|用語の意味を揃えたい | [`rumi_ai_1_10/docs/terminology.md`](./rumi_ai_1_10/docs/terminology.md) | `rule`、`skill`、`team workspace`、`subagent` 互換性のある名前の整理 |
|とにかく始めたい | [`README.md`](./README.md)の`Start` |最も短い起動コマンドのみがリストされています。
|ランタイム・カーネルの全体像を知りたい | [`rumi_ai_1_10/README.md`](./rumi_ai_1_10/README.md) |アーキテクチャとメインディレクトリの説明があります |
|コードを読まずに仕組みを理解したい | [`rumi_ai_1_10/docs/concepts/system-mechanism.md`](./rumi_ai_1_10/docs/concepts/system-mechanism.md) |起動、流れ、承認、付与の流れをテキストで追えます |
|まずは動作を確認したい（チュートリアル） | [`rumi_ai_1_10/docs/tutorials/runtime-quickstart.md`](./rumi_ai_1_10/docs/tutorials/runtime-quickstart.md) | `--health` から `/panel/` への最短ステップ |
| `rumi_viewer`を始めたい / ビューアがどのようにスタックするかを確認したい | [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) |起動手順、`401`、黒画面、`defaultspack`との関係まとめ |
|ビューア側を修正したい | [`rumi_viewer/src-tauri/src/config.rs`](./rumi_viewer/src-tauri/src/config.rs) および [`rumi_viewer/src-tauri/src/kernel_manager.rs`](./rumi_viewer/src-tauri/src/kernel_manager.rs) |ビューアは Tauri シェルであり、Rust 側はカーネルの起動を担当します。
|パック/defaultspackを使用したい | [`rumi_ai_1_10/ecosystem/defaultspack/README.md`](./rumi_ai_1_10/ecosystem/defaultspack/README.md) |これはチャット、ai_client、ツールなどのパック側の実装です。
| defaultspack のフロントエンドを拡張する方法を知りたい | [`rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md`](./rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md) |これは、右バーの追加、設定の追加、チャット レンダラーの拡張、プレビュー フィードの追加のためのゲートウェイです |
| API キーとシークレットの処理方法を知りたい | [`rumi_ai_1_10/docs/operations.md`](./rumi_ai_1_10/docs/operations.md)の秘密セクション | `user_data/secrets/`とAPIルートの説明があります |
|パックの作成方法を知りたい | [`rumi_ai_1_10/docs/pack-development.md`](./rumi_ai_1_10/docs/pack-development.md) |エコシステム.json、ルート、パーミッションのマナーをまとめました |
|運用や監査の概念を知りたい | [`rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`](./rumi_ai_1_10/docs/quality_pack/philosophy_memo.md) |継続的な開発と回帰確認のための前提を整理中 |

## リポジトリのレイアウト

- `rumi_ai_1_10/`: カーネル/ランタイム/API/バックエンド ソース ツリー
- `rumi_ai/`: バージョン安定した Python エントリポイント パッケージ
- `pack-shell/`: デスクトップ パック ランチャー
- `rumi_viewer/`: デスクトップ シェルとコントロール パネルのフロントエンド ソース
- `rumi_mobile/`: トラステッド LAN デフォルトパック アクセス用の Flutter iOS/Android アプリ
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/`:defaultspack にバンドルされているブラウザー コンパニオン アセット

## セットアップ

### 前提条件

- Python 3.10+
- Node.js 18+
-npm
- 錆び/積荷(`rumi_viewer`タッチ時)
- Flutter SDK（`rumi_mobile`使用時）

### クローンを作成してインストールする

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r rumi_ai_1_10/requirements.txt -r rumi_ai_1_10/requirements-dev.txt
pip install -e ./rumi_ai_1_10

cd rumi_viewer/frontend
npm install
cd ../..
```

## 開始

```bash
source .venv/bin/activate
python -m rumi_ai --health
python -m rumi_ai
```

`--health` では、システム ボリュームの使用状況もチェックします。 `disk` プローブが `DEGRADED` / `DOWN` である場合、コードの問題ではなく、空き領域の不足が原因である可能性があります。

## 一般的なタスク

### ショートカットだけ

`just` がインストールされている場合は、リポジトリのルートから一般的なチェックを利用できます。

```bash
just -l
just tooling-test
just integrity
```

### バックエンドのヘルスチェック

```bash
python -m rumi_ai --health
```

### ランタイム起動

```bash
python -m rumi_ai
```

### ビューアの開発

```bash
cd rumi_viewer/frontend
npm install
cd ..
cargo tauri dev
```

2回目以降は`rumi_viewer/frontend/node_modules`が残っている場合は以下の操作で開始できます。

```bash
cd rumi_viewer
cargo tauri dev
```

開発ビューアはリポジトリ内の `rumi_ai_1_10/` を自動的に検出し、カーネルを起動します。
`Open Defaultspack`は開発開始時にリポジトリに含まれる`defaultspack`を優先して開きます。
起動時にスタックする方法などのガイドについては、[`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md)を参照してください。

## 開発

```bash
source .venv/bin/activate
cd rumi_ai_1_10
python -m pytest tests/test_capability_trust_store.py
```

## クオリティパック

継続的な開発、監査、回帰確認のための運用パックについては、以下を参照してください。

- `rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`
- `rumi_ai_1_10/docs/quality_pack/claude_desktop_quality_pack.md`
- `rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh`

## HMAC の移行

```bash
python -m rumi_ai migrate-hmac
```

## コンポーネント

- `rumi_ai`: 安定した CLI とモジュール エントリポイント
- `rumi_ai_1_10`: カーネル、ランタイム、API、バックエンド、およびドキュメント
- `pack-shell`: デスクトップ パックを起動し、トークン/ブートストラップ フローを仲介します
- `rumi_viewer`: ビューア側アプリケーション シェルと正規パネル フロントエンド ソース
- `rumi_mobile`: ベアラー認証カーネル パック API のモバイル リモート クライアント
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/rumi_browser_companion`:defaultspack `browser_companion` ツール用のアンパックされた Chromium 拡張機能

アーキテクチャとランタイムの詳細については、[rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md)を参照してください。

Codex OSS にインスピレーションを得たコーディング ツールの規則については、[AGENTS.md](./AGENTS.md) および
[rumi_ai_1_10/docs/codex_oss_reference.md](./rumi_ai_1_10/docs/codex_oss_reference.md)。
