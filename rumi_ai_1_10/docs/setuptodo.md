# Rumi AI OS — セットアップ & デスクトップ配布 TODO

最終更新: 2026-03-16

パターン C アーキテクチャに基づくセットアップ実装ロードマップです。Rust ランチャー（薄い）が Kernel プロセスを管理し、セットアップ UI・コントロールパネル・Flow エディタ等は全て Pack が提供する Web UI です。React UI の実装はユーザーが担当します。

---

## 1. 設計決定事項

### 1.1 パターン C 採用

Rust ランチャー + Kernel + Pack の 3 層アーキテクチャを採用します。

- **Rust ランチャー**: PBS（python-build-standalone）構築、Kernel プロセス起動・ヘルスチェック・トレイアイコン・ブラウザ open の 5 つの責務のみを持つ薄いバイナリ
- **Kernel**: 既存の Python ランタイム。Flow 実行、Pack 管理、API サーバーの全てを担当
- **Pack**: セットアップ UI、コントロールパネル等の全ての UI 機能を Pack として提供

この設計の理由:
- **No Favoritism 原則との整合性**: UI フレームワークを強制しない。Pack が自由に選択可能
- **最小変更**: Kernel に UI 固有のロジックを持ち込まない
- **配布簡素化**: Rust バイナリ 1 つ + Python 環境 + ソースコード

### 1.2 IPC

既存の pack_api_server（HTTP localhost:8765）を使用します。新規の IPC 機構は追加しません。

### 1.3 profile.json

user_data/settings/profile.json にユーザープロフィールを保存します。セットアップ完了の判定はこのファイルの存在と setup_completed フラグで行います。

### 1.4 React UI はユーザーが作成

全ての Pack が提供する Web UI（セットアップ画面、コントロールパネル、Flow エディタ等）の React 実装はユーザーが担当します。エージェントは Python バックエンド + Flow 定義 + API エンドポイントまでを担当します。

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
│  ┌──────────────┐ ┌──────────────────┐ ┌──────────────┐  │
│  │ core_setup   │ │ core_control_panel│ │ marketplace  │  │
│  │ (Phase B)    │ │ (Phase C)         │ │ (Phase D/E)  │  │
│  └──────────────┘ └──────────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 3. profile.json スキーマ

```json
{
  "schema_version": 1,
  "initialized_at": "2026-03-16T12:00:00Z",
  "username": "",
  "language": "ja",
  "icon": null,
  "occupation": null,
  "setup_completed": true
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| schema_version | int | スキーマバージョン（将来のマイグレーション用） |
| initialized_at | string (ISO 8601) | セットアップ完了日時（UTC） |
| username | string | ユーザーネーム（必須、100文字以内） |
| language | string | 言語コード（ja, en, zh, ko, es, fr, de, pt, ru, ar） |
| icon | string or null | アイコン画像パスまたは URL |
| occupation | string or null | 職業 |
| setup_completed | bool | セットアップ完了フラグ |

---

## 4. Phase 構成

### R Phase: Rust ランチャー（担当: エージェント）

Rust 製の薄いランチャーバイナリ。責務は以下の 5 つのみ:

1. **PBS 構築**: python-build-standalone のダウンロード・展開・venv 作成・依存インストール
2. **Kernel 起動**: Python 子プロセスの spawn とライフサイクル管理
3. **ヘルスチェック**: localhost:8765 へのポーリングで Kernel の ready 状態を監視
4. **トレイアイコン**: システムトレイに常駐アイコンを表示（終了・再起動メニュー）
5. **ブラウザ open**: Kernel ready 後にデフォルトブラウザで Web UI を開く

タスク:
- R-1: Cargo プロジェクト初期化 + クロスプラットフォームビルド設定
- R-2: PBS ダウンロード・展開スクリプト（macOS / Windows / Linux）
- R-3: venv 作成 + uv pip install
- R-4: Kernel プロセス spawn + stdout/stderr パイプ
- R-5: ヘルスチェックループ（localhost:8765/health、タイムアウト 30s）
- R-6: システムトレイ（tray-icon crate）
- R-7: ブラウザ open（open crate）
- R-8: graceful shutdown（SIGTERM → Kernel 停止 → プロセス終了）

### Phase A: Kernel API 拡張（担当: エージェント）

- A-1: AppLifecycleManager 実装（起動状態管理、セットアップ状態チェック）
- A-2: pack_api_server エンドポイント追加
  - GET /health — ヘルスチェック
  - GET /api/setup/status — セットアップ状態
  - POST /api/setup/complete — セットアップ完了（core_setup.setup_wizard Flow 実行）
- A-3: 静的ファイル配信ミドルウェア（Pack 提供の Web UI を配信）

### Phase B: core_setup Pack（★ Python バックエンド実装済み）

Python バックエンド + Flow 定義は本プロンプトで実装済みです:
- core_runtime/core_pack/core_setup/ecosystem.json
- core_runtime/core_pack/core_setup/check_profile.py
- core_runtime/core_pack/core_setup/save_profile.py
- core_runtime/core_pack/core_setup/launch_setup_ui.py
- core_runtime/core_pack/core_setup/flows/setup_wizard.flow.yaml
- flows/00_startup.flow.yaml に setup_check + setup_launch_ui ステップ追加済み

残タスク:
- B-1: **React UI はユーザーが作成** — セットアップ画面（ユーザーネーム入力、言語選択、送信）
- B-2: pack_api_server との統合テスト

### Phase C: core_control_panel Pack（担当: エージェント + ユーザー）

ダッシュボード + Pack 管理 + Flow エディタ + 設定画面を提供する Pack。

- C-1: ecosystem.json 作成（pack_id: core_control_panel）
- C-2: ダッシュボード API エンドポイント（Pack 一覧、Flow 一覧、システム状態）
- C-3: Pack 管理 API（インストール、アンインストール、有効化/無効化）
- C-4: Flow エディタ API（Flow CRUD、ステップ編集、実行）
- C-5: 設定 API（profile.json 編集、環境設定）
- C-6: **React UI はユーザーが作成** — ダッシュボード、Pack 管理、Flow エディタ、設定画面

### Phase D: マーケットプレイス BE（担当: エージェント）

Cloudflare Workers + R2 + D1 + Supabase Auth によるバックエンド。

- D-1: Supabase Auth セットアップ（ユーザー認証、OAuth）
- D-2: D1 スキーマ設計（packs テーブル、versions、reviews、downloads）
- D-3: Cloudflare Workers API 実装（Pack 検索、詳細、ダウンロード URL 発行）
- D-4: R2 ストレージ設計（Pack アーカイブの保管、署名付き URL）
- D-5: Pack アップロード API（バリデーション、ハッシュ計算、R2 アップロード）
- D-6: レビュー・レーティング API

### Phase E: マーケットプレイス FE + ランチャー統合（担当: エージェント + ユーザー）

- E-1: マーケットプレイス Cloudflare Pages デプロイ設定
- E-2: **React UI はユーザーが作成** — マーケットプレイス Web UI（検索、詳細、インストール）
- E-3: core_control_panel からマーケットプレイス統合（Pack インストール UI）
- E-4: ランチャーからのマーケットプレイス直接アクセス

### Phase F: Pack 開発者 CLI（担当: エージェント）

- F-1: rumi-pack init — Pack スキャフォールド生成
- F-2: rumi-pack validate — ecosystem.json バリデーション
- F-3: rumi-pack build — Pack アーカイブ作成（.tar.gz）
- F-4: rumi-pack publish — マーケットプレイスへの公開
- F-5: rumi-pack test — Pack テスト実行

### Phase G: セキュリティ強化（担当: エージェント）

- G-1: Pack 署名検証（ed25519）
- G-2: コード署名（macOS notarization, Windows Authenticode）
- G-3: 自動アップデート機構（Rust ランチャー経由）
- G-4: CSP ヘッダー設定（Web UI のセキュリティ強化）

### Phase H: 収益化（担当: エージェント）

- H-1: 有料 Pack 課金基盤（Stripe 統合）
- H-2: サブスクリプション管理
- H-3: 収益分配ロジック（開発者 70% / プラットフォーム 30%）

---

## 5. 依存関係グラフ

```
R Phase ──────┐
              ▼
Phase A ◄──── Phase B (★実装済み)
  │               │
  ▼               ▼
Phase C ──── Phase D
  │               │
  ▼               ▼
Phase E ◄──── Phase F
  │
  ▼
Phase G ──── Phase H
```

- R Phase → Phase A: ランチャーが Kernel を起動できないと API が使えない
- Phase A → Phase B: API エンドポイントが必要（ただし Phase B の Python バックエンドは完了）
- Phase A → Phase C: API 拡張が前提
- Phase C → Phase E: コントロールパネルにマーケットプレイス統合
- Phase D → Phase E: BE が先、FE が後
- Phase D → Phase F: マーケットプレイスが存在しないと publish できない
- Phase E → Phase G: セキュリティ強化は配布基盤完成後
- Phase G → Phase H: セキュリティが確保されてから収益化

---

## 6. MVP 定義

最小構成 MVP: **R Phase + Phase A + Phase B + Phase C の最小構成**

MVP で実現すること:
- Rust ランチャーでアプリ起動
- 初回起動時にセットアップ画面を表示
- セットアップ完了後にコントロールパネルを表示
- Pack の一覧表示と有効化/無効化

---

## 7. 起動シーケンス

### 初回起動

```
1. Rust ランチャー起動
2. PBS 存在チェック → なければダウンロード・展開・venv 作成・依存インストール
3. Kernel プロセス spawn
4. ヘルスチェック (localhost:8765/health) → ready 待機
5. Kernel startup flow 実行:
   a. setup_check: profile.json チェック → needs_setup: true
   b. mounts_init → registry_load → ... (通常の起動シーケンス)
   c. setup_launch_ui: needs_setup なのでブラウザを開く
   d. interfaces_publish → emit_ready
6. ブラウザでセットアップ画面表示 (localhost:8765/setup)
7. ユーザーがフォーム入力 → POST /api/setup/complete
8. core_setup.setup_wizard Flow 実行 → profile.json 保存
9. セットアップ完了 → コントロールパネルへリダイレクト
```

### 通常起動（2回目以降）

```
1. Rust ランチャー起動
2. PBS 存在チェック → 存在する → スキップ
3. Kernel プロセス spawn
4. ヘルスチェック → ready 待機
5. Kernel startup flow 実行:
   a. setup_check: profile.json チェック → needs_setup: false
   b. mounts_init → registry_load → ... (通常の起動シーケンス)
   c. setup_launch_ui: needs_setup: false なのでスキップ
   d. interfaces_publish → emit_ready
6. ブラウザでコントロールパネル表示 (localhost:8765/)
```

---

## 8. インフラ構成

- **Cloudflare Pages**: マーケットプレイス Web UI のホスティング
- **Cloudflare Workers**: マーケットプレイス API
- **Cloudflare R2**: Pack アーカイブストレージ
- **Cloudflare D1**: Pack メタデータ DB
- **Supabase Auth**: ユーザー認証（OAuth: GitHub, Google）

---

## 9. 配布構成の設計メモ

### 9.1 macOS

```
RumiAI.app/
└── Contents/
    ├── MacOS/
    │   └── rumi-launcher      # Rust ランチャー
    ├── Resources/
    │   ├── python/             # PBS (python-build-standalone)
    │   ├── rumi_ai_1_10/      # ソースコードルート
    │   └── user_data/         # 初回起動時に作成
    └── Info.plist
```

### 9.2 Windows

```
RumiAI/
├── rumi-launcher.exe          # Rust ランチャー
├── python/                    # PBS
├── rumi_ai_1_10/              # ソースコードルート
└── user_data/                 # 初回起動時に作成
```

### 9.3 Linux

```
rumi-ai/
├── rumi-launcher              # Rust ランチャー
├── python/                    # PBS
├── rumi_ai_1_10/              # ソースコードルート
└── user_data/                 # 初回起動時に作成
```

---

## 10. Rust ランチャーの責務一覧（5つのみ）

1. **PBS 構築**: python-build-standalone のダウンロード・展開・venv 作成・依存インストール
2. **Kernel 起動**: Python 子プロセスの spawn とライフサイクル管理
3. **ヘルスチェック**: localhost:8765 へのポーリングで ready 状態を監視
4. **トレイアイコン**: システムトレイに常駐アイコンを表示
5. **ブラウザ open**: ready 後にデフォルトブラウザで Web UI を開く

ランチャーは UI を一切持ちません。全ての UI は Pack が提供する Web UI です。

---

## 11. 未決定事項

- セットアップで収集する項目の最終リスト（現在: username, language, icon, occupation）
- 言語パックの配布方式
- セットアップの「やり直し」機能の要否
- Windows での user_data パス（%APPDATA% vs 実行ファイル同階層）
- ビルド CI/CD パイプライン設計（GitHub Actions クロスプラットフォーム）
- Python バージョンの固定方針
- macOS codesigning / notarization
- Windows コード署名
- Pack の静的ファイル配信サーバーの実装方式
