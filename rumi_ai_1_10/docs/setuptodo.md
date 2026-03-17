# Rumi AI OS — セットアップ & デスクトップ配布 TODO

最終更新: 2026-03-17

パターン C アーキテクチャに基づくロードマップです。Rust ランチャー（薄い）が Kernel プロセスを管理し、セットアップ UI・コントロールパネル・Flow エディタ等は全て Pack が提供する Web UI（React）です。React UI の実装はユーザーが担当します。

---

## 1. 設計決定事項

### 1.1 パターン C 採用

Rust ランチャー + Kernel + Pack の 3 層アーキテクチャ。

- **Rust ランチャー**: PBS構築、Kernelプロセス管理、ヘルスチェック、トレイアイコン、ブラウザ open の 5 責務のみ
- **Kernel**: Python ランタイム。Flow 実行、Pack 管理、API サーバー
- **Pack**: 全ての UI 機能を Pack として提供（React Web UI）

### 1.2 認証・データ保存

- **認証**: Supabase Auth（OAuth のみ: Google / GitHub）。メール/パスワード認証はなし
- **プロフィールデータ保存**: Cloudflare KV（Supabase には保存しない）
- **ローカルプロフィール**: user_data/settings/profile.json

### 1.3 IPC

既存の pack_api_server（HTTP localhost:8765）を使用。新規 IPC 不要。

### 1.4 UI 方針

- 全ての Web UI は React + TSX で作成
- React UI はユーザーが担当。エージェントは Python バックエンド + Flow + API + Rust のみ
- ランチャーのフロントエンド（コントロールパネル）も React

### 1.5 アイコン方針

- プリセットアイコンのみ（ユーザーのオリジナルアイコンアップロードは未対応）
- icon フィールドにはプリセットの ID 文字列を保存（例: "cat", "avatar_03"）
- 画像ファイルはローカルに保存。サイトから ID を受け取り、対応する画像を表示

---

## 2. アーキテクチャ概要

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

| フィールド | 型 | 説明 |
|-----------|-----|------|
| schema_version | int | スキーマバージョン |
| initialized_at | string (ISO 8601) | セットアップ完了日時 |
| username | string | ユーザーネーム（必須、100文字以内） |
| language | string | 言語コード（ja, en, zh, ko, es, fr, de, pt, ru, ar） |
| icon | string or null | プリセットアイコン ID |
| occupation | string or null | 職業 |
| setup_completed | bool | セットアップ完了フラグ |

---

## 4. 進行状況

### 完了済み

| タスク | 内容 |
|--------|------|
| コードレビュー | C+ ランク。セキュリティ・アーキテクチャの問題を特定 |
| SEC-1 | secure_executor.py: Docker image ダイジェスト固定 + _sanitize_context 強化 |
| SEC-2 | python_file_executor.py: Docker image ダイジェスト固定 |
| APP-1 | app.py: permissive ガード強化（ホワイトリスト方式） |
| 調査 1 | Python 梱包: PBS + uv で CONDITIONAL GO |
| 調査 2 | コントロールパネル + ランチャー + マーケットプレイス構想 |
| 調査 3 | Pack + Flow でセットアップ実現可否 → パターン C 採用 |
| Phase B | core_setup Pack Python バックエンド + Flow 定義 |
| Phase A | Kernel API 拡張: /health, /api/setup/status, /api/setup/complete, 静的ファイル配信 |
| サイトデプロイ | Cloudflare Pages (rumi-setup.pages.dev) |
| サイト認証 | Supabase Auth OAuth (Google / GitHub) 動作確認済み |

### 進行中

| タスク | 担当 | 内容 |
|--------|------|------|
| サイト仕上げ | ユーザー | ダミーフォーム削除、言語10言語化、職業追加、KV保存実装 |
| アプリ連携承認画面 | ユーザー | /authorize ページ（設計確定、実装待ち） |
| プリセットアイコン作成 | ユーザー | ID命名 + 画像作成 |

### 未着手

| タスク | 担当 | 内容 |
|--------|------|------|
| R Phase | エージェント(Rust) + ユーザー(React) | Rust ランチャー + アップデート機構 |
| Phase C | エージェント(Python) + ユーザー(React) | core_control_panel Pack |
| Phase U | エージェント | アップデート機構 |
| Phase D/E | エージェント + ユーザー | マーケットプレイス（最後に回す） |
| Phase F | エージェント | Pack 開発者 CLI |
| Phase G | エージェント | セキュリティ強化 |

---

## 5. Phase 構成

### R Phase: Rust ランチャー（担当: エージェント + ユーザー）

Rust 製の薄いランチャーバイナリ。

**エージェント担当:**

- R-1: Cargo プロジェクト初期化 + クロスプラットフォームビルド設定
- R-2: PBS ダウンロード・展開（macOS / Windows / Linux）
- R-3: venv 作成 + uv pip install
- R-4: Kernel プロセス spawn + stdout/stderr パイプ
- R-5: ヘルスチェックループ（localhost:8765/health、タイムアウト 30s）
- R-6: システムトレイ（tray-icon crate）
- R-7: ブラウザ open（open crate）
- R-8: graceful shutdown（SIGTERM → Kernel 停止 → プロセス終了）

**ユーザー担当:**

- なし（ランチャー自体は UI を持たない。UIは core_control_panel の React）

### Phase A: Kernel API 拡張 ★完了

- GET /health — ヘルスチェック（認証不要）
- GET /api/setup/status — セットアップ状態（認証不要）
- POST /api/setup/complete — セットアップ完了（認証不要）
- 静的ファイル配信ミドルウェア
- AppLifecycleManager

### Phase B: core_setup Pack ★Python バックエンド完了

**完了:**

- ecosystem.json, check_profile.py, save_profile.py, launch_setup_ui.py
- setup_wizard.flow.yaml, 00_startup.flow.yaml 修正

**残タスク（ユーザー担当）:**

- B-1: サイト仕上げ（ダミーフォーム削除、言語10言語化、職業追加）
- B-2: Cloudflare KV プロフィール保存実装
- B-3: アプリ連携承認画面（/authorize）
- B-4: プリセットアイコン作成

### Phase C: core_control_panel Pack（担当: エージェント + ユーザー）

ダッシュボード + Pack 管理 + Flow エディタ + 設定画面 + アップデート確認。

**エージェント担当（Python バックエンド）:**

- C-1: ecosystem.json 作成
- C-2: ダッシュボード API（Pack 一覧、Flow 一覧、システム状態）
- C-3: Pack 管理 API（インストール、アンインストール、有効化/無効化）
- C-4: Flow エディタ API（Flow CRUD、ステップ編集、実行）
- C-5: 設定 API（profile.json 編集、環境設定）
- C-6: アップデート確認 API

**ユーザー担当（React UI）:**

- C-7: ダッシュボード画面
- C-8: Pack 管理画面（Steam ライブラリ風）
- C-9: Flow エディタ画面（React Flow）
- C-10: 設定画面
- C-11: アップデート画面

### Phase U: アップデート機構（担当: エージェント）

- U-1: バージョン管理（現在のバージョン、最新バージョンの取得）
- U-2: アップデートチェック API（Cloudflare Workers or R2 のバージョンファイル）
- U-3: Rust ランチャーのセルフアップデート
- U-4: Kernel（Python）のアップデート（ソースコード差し替え）
- U-5: Pack のアップデート

### Phase D: マーケットプレイス BE（最後に回す）

Cloudflare Workers + R2 + D1 + Supabase Auth

### Phase E: マーケットプレイス FE（最後に回す）

Cloudflare Pages + ランチャー内統合

### Phase F: Pack 開発者 CLI

rumi-pack init / validate / build / publish / test

### Phase G: セキュリティ強化

Pack 署名検証、コード署名、CSP ヘッダー

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

## 7. MVP 定義

MVP = R Phase + Phase A + Phase B + Phase C の最小構成 + Phase U（アップデート）。マーケットプレイスなし。

---

## 8. アプリ連携フロー

### セットアップ時の流れ

1. デスクトップアプリがブラウザで `https://rumi-setup.pages.dev/authorize?callback=http://localhost:8765/api/setup/complete` を開く
2. サイト側でログイン済みか確認 → 未ログインなら /login → ログイン済みなら承認画面
3. 承認画面: 「このアプリにプロフィール情報を送信しますか？」
4. 承認 → fetch で localhost:8765/api/setup/complete に POST
5. アプリ側で profile.json 保存 → セットアップ完了

### POST /api/setup/complete の JSON

```json
{
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer"
}
```

---

## 9. 起動シーケンス

### 初回起動

1. Rust ランチャー起動
2. PBS チェック → なければダウンロード・展開・venv 作成・依存インストール
3. Kernel spawn → ヘルスチェック → ready 待機
4. startup flow: setup_check → needs_setup: true
5. ブラウザで rumi-setup.pages.dev/authorize を開く
6. ユーザーが承認 → localhost:8765 に POST → profile.json 保存
7. セットアップ完了 → コントロールパネル表示

### 通常起動

1. Rust ランチャー起動
2. PBS チェック → 存在 → スキップ
3. Kernel spawn → ヘルスチェック → ready
4. startup flow: setup_check → needs_setup: false
5. ブラウザでコントロールパネル表示

---

## 10. インフラ構成

| サービス | 用途 |
|----------|------|
| Cloudflare Pages | サイト (rumi-setup.pages.dev) |
| Cloudflare KV | プロフィールデータ保存 |
| Cloudflare Workers | アップデートチェック API、将来のマーケットプレイス API |
| Cloudflare R2 | PBS/uv 配布、将来の Pack 配布 |
| Cloudflare D1 | 将来のマーケットプレイス DB |
| Supabase Auth | ユーザー認証（OAuth: Google / GitHub） |

---

## 11. 配布構成

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

### Windows

```
RumiAI/
├── rumi-launcher.exe
├── python/
├── rumi_ai_1_10/
└── user_data/
```

### Linux

```
rumi-ai/
├── rumi-launcher
├── python/
├── rumi_ai_1_10/
└── user_data/
```

---

## 12. 未決定事項

- セットアップ収集項目の最終リスト
- 言語パックの配布方式
- セットアップの「やり直し」機能
- Windows での user_data パス
- ビルド CI/CD パイプライン
- Python バージョン固定方針
- macOS codesigning / notarization
- Windows コード署名
- core_control_panel の Web UI 配信方法
- Rust ランチャーの crate 選定
- Pack 開発者 CLI の言語
- アップデートのバージョンファイル形式・配布方法
