<!-- docs-i18n-links:start -->
[EN](../../setuptodo.md) | [JP](./setuptodo.md) | [KR](../ko/setuptodo.md) | [CN](../zh-cn/setuptodo.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — セットアップとデスクトップ配布 TODO

> **レガシー計画メモ**: 実装計画の履歴。現在のポリシーについては、[roadmap.md](./roadmap.md) および [docs/README.md](./README.md)を参照してください。

最終更新日: 2026-03-17

パターン C アーキテクチャに基づくロードマップ。カーネルプロセスはRustランチャー(シン)で管理されており、セットアップUI、コントロールパネル、フローエディタ等は全てPackが提供するWeb UI(React)です。 React UI の実装はお客様の責任です。

---

## 1. 設計上の決定

### 1.1 パターン C を採用する

3 層アーキテクチャ: Rust Launcher + カーネル + パック。

- **Rust Launcher**: たった 5 つの役割: PBS 構築、カーネルプロセス管理、ヘルスチェック、トレイアイコン、ブラウザーオープン
- **カーネル**: Python ランタイム。フロー実行、パック管理、APIサーバー
- **Pack**: すべての UI 機能をパックとして提供します (React Web UI)

### 1.2 認証/データストレージ

- **認証**: Supabase 認証 (OAuth のみ: Google / GitHub)。メール/パスワード認証なし
- **プロファイル データの保存**: Cloudflare KV (Supabase には保存されません)
- **ローカル プロファイル**: user_data/settings/profile.json

### 1.3 IPC

既存の Pack_api_server (HTTP localhost:8765) を使用します。新しい IPC は必要ありません。

### 1.4 UI ポリシー

- すべての Web UI は React + TSX で作成されています
- React UI はユーザーの手にあります。エージェントは Python バックエンド + Flow + API + Rust のみ
- ランチャーのフロントエンド(コントロールパネル)もReactです

### 1.5 アイコンポリシー

- プリセットアイコンのみ（ユーザーオリジナルアイコンのアップロードはサポートされていません）
- アイコンフィールドには、プリセットされたID文字列（例：「cat」、「avatar_03」）が保存されます。
- 画像ファイルはローカルに保存されます。サイトからIDを受け取り、対応する画像を表示

---

## 2. アーキテクチャの概要

```
┌──────────────────────────────────────────────────────────┐
│                    Rust ランチャー                         │
│  (PBS構築 / Kernel起動 / ヘルスチェック / トレイ / open)      │
└───────┬──────────────────────────────────┬────────────────┘
        │ spawn                            │ open browser
        ▼                                  ▼
┌──────────────────────┐        ┌──────────────────────┐
│       Kernel         │        │    ブラウザ (Web UI)    │
│  (Python runtime)    │◄──────►│   React SPA           │
│                      │  HTTP  │   localhost:8765      │
│  ┌────────────────┐  │        └──────────────────────┘
│  │ pack_api_server │  │
│  │ :8765           │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Flow Engine    │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Pack Manager   │  │
│  └────────────────┘  │
└──────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                         Packs                             │
│  ┌──────────────┐ ┌──────────────────┐                   │
│  │ core_setup   │ │ core_control_panel│                   │
│  │ (Phase B)    │ │ (Phase C)         │                   │
│  └──────────────┘ └──────────────────┘                   │
└──────────────────────────────────────────────────────────┘
```

---

## 3. profile.json スキーマ

```json
{
  "schema_version": 1,
  "initialized_at": "2026-03-17T12:00:00Z",
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer",
  "setup_completed": true
}
```

|フィールド |タイプ |説明 |
|-----------|-----|------|
|スキーマ_バージョン |整数 |スキーマのバージョン |
|初期化済み_at |文字列 (ISO 8601) |セットアップ完了日時 |
|ユーザー名 |文字列 |ユーザー名 (必須、最大 100 文字) |
|言語 |文字列 |言語コード (ja、en、zh、ko、es、fr、de、pt、ru、ar) |
|アイコン |文字列またはnull |プリセットアイコンID |
|職業 |文字列またはnull |職業 |
|セットアップ_完了 |ブール |セットアップ完了フラグ |

---

## 4. 進捗状況

### 完了

|タスク |目次 |
|--------|------|
|コードレビュー | C+ランク。セキュリティ アーキテクチャの問題を特定する |
| SEC-1 | secure_executor.py: Docker イメージ ダイジェストの修正 + _sanitize_context の強化 |
| SEC-2 | python_file_executor.py: Docker イメージのダイジェストが修正されました |
| APP-1 | app.py: 寛容なガード強化 (ホワイトリスト方式) |
|調査1 | Python パッケージ化: PBS + uv を使用した CONDITIONAL GO |
|調査2 |コントロールパネル + ランチャー + マーケットプレイスのコンセプト |
|調査3 | Pack+Flowでのセットアップは可能ですか？ →パターンCを採用 |
|フェーズB | core_setup パック Python バックエンド + フロー定義 |
|フェーズA |カーネル API 拡張機能: /health、/api/setup/status、/api/setup/complete、静的ファイル配信 |
|サイトの展開 | Cloudflare ページ (rumi-setup.pages.dev) |
|サイト認証 | Supabase Auth OAuth (Google / GitHub) 動作確認済み |

### 進行中

|タスク |責任 |目次 |
|--------|------|------|
|現場仕上げ |ユーザー |ダミーフォーム削除、10言語化、職業追加、KVストレージ実装 |
|アプリ連携承認画面 |ユーザー | /authorize ページ (デザインが完成し、実装を待っています) |
|プリセットアイコン作成 |ユーザー | IDネーミング+イメージ作成 |

### 未開始

|タスク |責任 |目次 |
|--------|------|------|
| Rフェーズ |エージェント (Rust) + ユーザー (React) | Rust ランチャー + アップデートメカニズム |
|フェーズ C |エージェント (Python) + ユーザー (React) | core_control_panel パック |
|フェーズ U |エージェント |更新メカニズム |
|フェーズ D/E |エージェント + ユーザー |マーケットプレイス (最終ターン) |
|フェーズ F |エージェント |パック開発者 CLI |
|フェーズG |エージェント |セキュリティ強化 |

---

## 5. フェーズ構成

### R フェーズ: Rust Launcher (担当者: エージェント + ユーザー)

Rust で作られた薄型ランチャー バイナリ。

**担当エージェント:**

- R-1: Cargo プロジェクトの初期化 + クロスプラットフォーム ビルド設定
- R-2: PBS ダウンロード/解凍 (macOS / Windows / Linux)
- R-3: venv 作成 + uv pip インストール
- R-4: カーネルプロセス生成 + stdout/stderr パイプ
- R-5: ヘルスチェックループ (localhost:8765/health、タイムアウト 30 秒)
- R-6: システムトレイ (トレイアイコンクレート)
- R-7: ブラウザを開く (クレートを開く)
- R-8: 正常なシャットダウン (SIGTERM → カーネル停止 → プロセス終了)

**ユーザー責任:**

- なし (ランチャー自体に UI はありません。UI は core_control_panel React です)

### フェーズ A: カーネル API 拡張 ★完了

- GET /health — ヘルスチェック (認証は必要ありません)
- GET /api/setup/status — セットアップステータス (認証は必要ありません)
- POST /api/setup/complete — セットアップが完了しました (認証は必要ありません)
- 静的ファイル配布ミドルウェア
- AppLifecycleManager

### フェーズ B: core_setup パック ★Python バックエンドが完成

**完了:**

- エコシステム.json、check_profile.py、save_profile.py、launch_setup_ui.py
- setup_wizard.flow.yaml、00_startup.flow.yamlを修正

**残りのタスク (ユーザーの責任):**

- B-1：サイト仕上げ（ダミーフォーム削除、10言語追加、職業追加）
- B-2: Cloudflare KV プロファイルストレージの実装
- B-3：アプリ連携承認画面（/authorize）
- B-4: プリセットアイコンの作成

### フェーズ C: core_control_panel パック (担当者: エージェント + ユーザー)

ダッシュボード＋パック管理＋フローエディタ＋設定画面＋アップデート確認。

**担当エージェント (Python バックエンド):**

- C-1: エコシステム.json を作成する
- C-2: ダッシュボード API (パックリスト、フローリスト、システムステータス)
- C-3: パック管理 API (インストール、アンインストール、有効化/無効化)
- C-4: フローエディターAPI (フローCRUD、ステップ編集、実行)
- C-5: 設定API（profile.json編集、環境設定）
- C-6: 更新確認API

**ユーザー責任 (React UI):**

- C-7: ダッシュボード画面
- C-8：パック管理画面（Steamライブラリ風）
・C-9：フローエディタ画面（React Flow）
- C-10：設定画面
- C-11: 更新画面

### フェーズ U: 更新メカニズム (担当: エージェント)

- U-1: バージョン管理 (現在のバージョン、最新バージョンの取得)
- U-2: 更新チェックAPI (Cloudflare WorkersまたはR2バージョンファイル)
- U-3: Rust ランチャーの自己アップデート
- U-4: カーネル(Python)アップデート(ソースコード置き換え)
- U-5: パックのアップデート

### フェーズ D: マーケットプレイス BE (最後のターン)

Cloudflare ワーカー + R2 + D1 + Supabase 認証

### フェーズ E: マーケットプレイス FE (最終ターン)

Cloudflare ページ + ランチャー内統合

### フェーズ F: パック開発者 CLI

rumi-pack 初期化 / 検証 / ビルド / 公開 / テスト

### フェーズ G: セキュリティの強化

パック署名検証、コード署名、CSP ヘッダー

---

## 6. 依存関係

```
R Phase ──────┐
              ▼
Phase A ★完了  Phase B ★Python完了（React残り）
  │               │
  ▼               ▼
Phase C ──── Phase U
  │
  ▼
Phase F ──── Phase G
  │
  ▼
Phase D ──── Phase E（最後）
```

---

## 7. MVP の定義

MVP = R フェーズ + フェーズ A + フェーズ B + フェーズ C + フェーズ U の最小構成 (更新)。マーケットプレイスはありません。

---

## 8. アプリ連携の流れ

### セットアップの流れ

1. デスクトップ アプリがブラウザで `https://rumi-setup.pages.dev/authorize?callback=http://localhost:8765/api/setup/complete` を開きます
2.サイトにログインしているか確認→ログインしていない場合は/login→ログインしている場合は承認画面
3. 承認画面：「プロフィール情報をこのアプリに送信しますか？」
4. 認可 → localhost:8765/api/setup/complete with fetch に POST
5.アプリ側にprofile.jsonを保存→セットアップ完了

### POST の JSON /api/setup/complete

```json
{
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer"
}
```

---

## 9. ブートシーケンス

### 最初の起動

1.Rustランチャーを起動します
2. PBS チェック → そうでない場合は、ダウンロード、抽出、venv の作成、依存関係のインストール
3. カーネルの生成 → ヘルスチェック → 準備完了
4. 起動フロー：setup_check→needs_setup：true
5. ブラウザで rumi-setup.pages.dev/authorize を開きます
6. ユーザーが承認 → localhost:8765 に POST → profile.json を保存
7. セットアップ完了 → コントロールパネル表示

### 通常起動

1.Rustランチャーを起動します
2. PBSチェック→存在→スキップ
3. カーネルの生成 → ヘルスチェック → 準備完了
4. 起動フロー：setup_check→needs_setup：false
5.ブラウザにコントロールパネルを表示する

---

## 10. インフラストラクチャ構成

|サービス |アプリケーション |
|----------|------|
| Cloudflareのページ |サイト (rumi-setup.pages.dev) |
|クラウドフレア KV |プロフィールデータの保存 |
| Cloudflare ワーカー |更新チェック API、将来のマーケットプレイス API |
|クラウドフレア R2 | PBS/uv 配布、将来のパック配布 |
|クラウドフレア D1 |フューチャーマーケットプレイスDB |
|スーパーベース認証 |ユーザー認証（OAuth：Google / GitHub） |

---

## 11. ディストリビューション構成

### macOS

```
RumiAI.app/Contents/
├── MacOS/rumi-launcher
├── Resources/
│   ├── python/          # PBS
│   ├── rumi_ai_1_10/   # ソースコード
│   └── user_data/       # 初回起動時作成
└── Info.plist
```

### ウィンドウ

```
RumiAI/
├── rumi-launcher.exe
├── python/
├── rumi_ai_1_10/
└── user_data/
```

### リナックス

```
rumi-ai/
├── rumi-launcher
├── python/
├── rumi_ai_1_10/
└── user_data/
```

---

##12.未定事項

- セットアップコレクションアイテムの最終リスト
・言語パックの配布方法
- 「元に戻す」機能の設定
- Windows の user_data パス
- CI/CD パイプラインの構築
- Python バージョン修正ポリシー
- macOS コード署名 / 公証
- Windows コード署名
- core_control_panelのWeb UI配信方法
- Rustランチャークレートの選択
- パック開発者 CLI 言語
- アップデート版のファイル形式と配布方法
