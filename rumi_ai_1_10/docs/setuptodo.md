# Rumi AI OS — セットアップ実装 TODO

最終更新: 2026-03-16

デスクトップアプリの初回セットアップ機能と Tauri ビルド時の Python/venv 梱包に関するタスク管理ドキュメントです。セットアップ画面でユーザー情報を収集し、`user_data/settings/profile.json` に保存することで初回セットアップ完了とします。Python 実行環境は python-build-standalone を Tauri resources として梱包し、PyInstaller は使用しません。

---

## 1. 設計決定事項

### 1.1 セットアップ方式

ハイブリッド方式を採用します。Kernel が `profile.json` の存在をチェックする最小ブートストラップと、セットアップロジックを担う `core_setup` Pack の組み合わせです。

- **コア最小ブートストラップ**: Kernel 起動時に `user_data/settings/profile.json` の存在を確認し、未存在ならセットアップ未完了と判定する
- **core_setup Pack**: セットアップデータのバリデーションと保存を担当する Pack。Flow として定義し、validate → save の 2 phase で実行する

### 1.2 Python 梱包

python-build-standalone を使用します。OS ごとにビルドスクリプトがアーカイブをダウンロード・展開し、Tauri の `bundle.resources` に登録します。PyInstaller は使用しません。

- **配布形式**: python-build-standalone のプレビルドバイナリ
- **依存インストール**: `uv pip install` で venv に依存をインストール
- **Tauri 登録**: `tauri.conf.json` の `bundle.resources` にパスを登録

### 1.3 IPC

既存の `pack_api_server`（HTTP localhost:8765）を使用します。新規の IPC 機構は追加しません。セットアップ用エンドポイントを `pack_api_server` に追加します。

### 1.4 セットアップデータ保存先

`user_data/settings/profile.json` に保存します。セットアップ完了の判定はこのファイルの存在チェックで行います。

### 1.5 セットアップ UI フレームワーク

React/TSX でユーザーが実装します。エージェントは Rust ⇔ React ブリッジ（Tauri コマンド・TypeScript 型定義）までを担当し、UI コンポーネントの実装はユーザーに委ねます。

### 1.6 Pack が使用するデスクトップ UI フレームワーク

強制しません。Tauri / Electron / その他は Pack の選択に任せます。公式コアは UI フレームワークを規定しません（No Favoritism 原則）。

### 1.7 Tauri 統合タイミング

Tauri は最後に統合します。Phase A〜D の基盤が完成してから Tauri ビルドに統合する方針です。

---

## 2. タスク一覧

### Phase A: Python 梱包基盤（担当: エージェント）

#### A-1: ビルドスクリプト作成 — python-build-standalone ダウンロード

OS を検出し（macOS / Windows / Linux）、対応する python-build-standalone のアーカイブを選択してダウンロード・展開するビルドスクリプトを作成します。

- OS 検出（`uname -s` / PowerShell 等）
- アーカイブ URL の選択（OS × アーキテクチャ）
- ダウンロード（`curl` / `wget`）
- 展開（`tar` / `unzip`）
- 展開先ディレクトリの標準化

#### A-2: ビルドスクリプト作成 — 依存インストール

`uv pip install` を使用して、展開した Python 環境に依存パッケージをインストールするスクリプトを作成します。

- `uv` の存在確認とインストール
- venv 作成（python-build-standalone 上）
- `uv pip install -r requirements.lock` の実行
- インストール結果の検証

#### A-3: tauri.conf.json 設定

Tauri のビルド設定に Python 環境を `bundle.resources` として登録します。

- `tauri.conf.json` の `bundle.resources` に Python ディレクトリパスを追加
- OS 別のリソースパス設定
- ビルド時のコピー設定

#### A-4: Rust 側 Python プロセス起動ロジック

Tauri の Rust バックエンドから Python プロセスを起動するロジックを実装します。

- `tauri::api::process` または `std::process::Command` による子プロセス管理
- `resource_dir()` からの Python バイナリパス解決
- プロセスのライフサイクル管理（起動・監視・終了）
- 起動失敗時のエラーハンドリング

### Phase B: ブートストラップ（担当: エージェント）

#### B-1: Kernel にセットアップ状態チェック追加

Kernel 起動時に `user_data/settings/profile.json` の存在をチェックし、セットアップ状態を判定するロジックを追加します。

- `profile.json` の存在チェック
- `schema_version` の検証
- `setup_completed` フラグの確認
- セットアップ未完了時の状態通知

#### B-2: pack_api_server にセットアップ用エンドポイント追加

`pack_api_server` に以下のエンドポイントを追加します。

- `GET /api/setup/status` — セットアップ状態を返す（`completed: bool`, `schema_version: int`）
- `POST /api/setup/complete` — セットアップデータを受け取り、`core_setup` Flow を実行して `profile.json` を保存する

### Phase C: core_setup Pack（担当: エージェント）

#### C-1: core_setup Pack 作成

セットアップロジックを担う Pack を作成します。

- `ecosystem.json` — Pack メタデータ（pack_id: `core_setup`、provides 等）
- `validate_profile.py` — 入力データのバリデーション（ユーザーネーム、言語コード等）
- `save_profile.py` — バリデーション済みデータを `profile.json` に保存

#### C-2: core_setup Flow 定義

validate → save の 2 phase で実行する Flow を定義します。

- Phase 1（validate）: `validate_profile.py` で入力を検証
- Phase 2（save）: `save_profile.py` で `profile.json` に書き込み
- エラーハンドリング: バリデーション失敗時は save をスキップ

### Phase D: Rust ⇔ React ブリッジ（担当: エージェント）

#### D-1: Tauri コマンド定義

Tauri の `#[tauri::command]` で以下のコマンドを定義します。

- `check_setup_status` — `GET /api/setup/status` を内部呼び出しし、セットアップ状態を返す
- `submit_setup` — セットアップデータを受け取り `POST /api/setup/complete` を内部呼び出しする

#### D-2: TypeScript 型定義

フロントエンドで使用する型を定義します。

- `SetupStatus` — `{ completed: boolean; schema_version: number }`
- `SetupInput` — `{ username: string; language: string }`
- `SetupResult` — `{ success: boolean; error?: string }`

### Phase E: セットアップ UI（担当: ユーザー）

#### E-1: セットアップ画面の React コンポーネント作成

セットアップ画面の UI コンポーネントを React/TSX で作成します。エージェントが提供する TypeScript 型定義と Tauri コマンドを使用します。

#### E-2: セットアップフローの状態管理

セットアップの進行状態（入力中 → 送信中 → 完了 / エラー）を管理する状態ロジックを実装します。

### Phase F: テスト（担当: エージェント）

#### F-1: core_setup Pack のユニットテスト

`validate_profile.py` と `save_profile.py` の単体テストを作成します。

- 正常系: 有効な入力でのバリデーション成功・保存成功
- 異常系: 空文字、不正な言語コード、過長文字列等
- エッジケース: 既存 `profile.json` の上書き

#### F-2: セットアップ Flow の統合テスト

`core_setup` Flow 全体の統合テストを作成します。

- validate → save の正常フロー
- バリデーション失敗時の save スキップ
- Flow の冪等性（2 回実行しても問題ないこと）

#### F-3: ビルドスクリプトのテスト

Python 梱包ビルドスクリプトのテストを作成します。

- OS 検出の正確性
- ダウンロード URL の妥当性
- 展開後のディレクトリ構造の検証

---

## 3. 依存関係グラフ

```
A-1 → A-2 → A-3 → A-4
                     ↓
B-1 → B-2 ← C-1 → C-2
       ↓
D-1 → D-2 → E-1 → E-2
       ↓
F-1, F-2, F-3
```

- **A-1 → A-2**: ダウンロード・展開が完了しないと依存インストールできない
- **A-2 → A-3**: Python 環境のパスが確定しないと `tauri.conf.json` に登録できない
- **A-3 → A-4**: Tauri resources 設定が完了しないと Rust 側のパス解決ロジックを書けない
- **A-4 → B-2**: Python プロセス起動ができないと API サーバーが動かない
- **B-1 → B-2**: セットアップ状態チェックが先、エンドポイント追加が後
- **C-1 → B-2**: core_setup Pack が存在しないとエンドポイントから呼び出せない
- **C-1 → C-2**: Pack のファイルが揃わないと Flow を定義できない
- **B-2 → D-1**: API エンドポイントが存在しないと Tauri コマンドから呼び出せない
- **D-1 → D-2**: コマンド定義が先、型定義はコマンドの入出力に合わせる
- **D-2 → E-1**: 型定義が揃わないと UI コンポーネントを型安全に書けない
- **E-1 → E-2**: コンポーネントが存在しないと状態管理を組み込めない
- **B-2 → F-1, F-2, F-3**: テストは対象の実装完了後に作成（ただし各 Phase と並行可能）

---

## 4. 配布構成の設計メモ

### 4.1 macOS .app バンドルのディレクトリ構造

```
RumiAI.app/
└── Contents/
    ├── MacOS/
    │   └── rumi-ai            # Tauri バイナリ
    ├── Resources/
    │   ├── python/
    │   │   ├── bin/
    │   │   │   └── python3    # python-build-standalone
    │   │   └── lib/
    │   │       └── python3.x/
    │   │           └── site-packages/
    │   ├── rumi_ai_1_10/      # ソースコードルート
    │   │   ├── core_runtime/
    │   │   ├── backend_core/
    │   │   └── ...
    │   └── user_data/         # 初回起動時に作成
    │       └── settings/
    │           └── profile.json
    └── Info.plist
```

### 4.2 Windows のディレクトリ構造

```
RumiAI/
├── rumi-ai.exe                # Tauri バイナリ
├── python/
│   ├── python.exe             # python-build-standalone
│   └── Lib/
│       └── site-packages/
├── rumi_ai_1_10/              # ソースコードルート
│   ├── core_runtime/
│   ├── backend_core/
│   └── ...
└── user_data/                 # 初回起動時に作成
    └── settings/
        └── profile.json
```

### 4.3 起動シーケンス

```
1. Tauri バイナリ起動
   ↓
2. resource_dir() から Python バイナリパスを解決
   ↓
3. Python 子プロセスを起動（pack_api_server）
   ↓
4. API ready 待機（localhost:8765 へのヘルスチェック）
   ↓
5. WebView 起動（React フロントエンド）
   ↓
6. フロントエンドが GET /api/setup/status を呼び出し
   ↓
7a. setup_completed=true → メイン画面へ
7b. setup_completed=false → セットアップ画面へ
```

> **注意**: デスクトップ配布では Docker 非搭載環境が多いため、セキュリティモードは `permissive` が必要になります。`RUMI_SECURITY_MODE=permissive` を設定してください。APP-1 でガード強化済みの場合は `RUMI_ALLOW_PERMISSIVE=true` の環境変数設定も必要です。

---

## 5. profile.json の推奨構造

```json
{
  "schema_version": 1,
  "initialized_at": "2026-03-15T12:00:00Z",
  "username": "haru",
  "language": "ja",
  "setup_completed": true
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `schema_version` | `int` | スキーマバージョン。将来のマイグレーション用 |
| `initialized_at` | `string` (ISO 8601) | セットアップ完了日時（UTC） |
| `username` | `string` | ユーザーネーム |
| `language` | `string` | 言語コード（`ja`, `en` 等） |
| `setup_completed` | `bool` | セットアップ完了フラグ |

---

## 6. 未決定事項

以下の項目は現時点で未決定です。実装を進める中で順次決定します。

- **セットアップで収集する項目の最終リスト** — 現在はユーザーネームと言語のみ。テーマ設定、通知設定、AI プロバイダー設定等を追加するか検討中
- **言語パックの配布方式** — アプリバンドルに全言語を同梱するか、初回セットアップ時にダウンロードするか
- **セットアップの「やり直し」機能の要否** — `profile.json` を削除して再セットアップを許可するか。設定画面からリセットできるようにするか
- **pack_api_server のセットアップ用エンドポイントの認証方式** — localhost 限定のため認証不要とするか、トークン認証を追加するか
- **Windows での user_data パス** — `%APPDATA%\RumiAI\user_data` とするか、実行ファイルと同階層にするか
- **デスクトップ配布での Docker 前提の有無** — permissive モードを前提とするか、将来的に Docker Desktop 連携を検討するか
- **ビルド CI/CD パイプライン** — GitHub Actions でのクロスプラットフォームビルドの設計
- **Python バージョンの固定方針** — python-build-standalone の特定バージョンに固定するか、最新安定版を追従するか
- **macOS codesigning / notarization** — Apple Developer Program への登録と署名フローの設計
- **Windows コード署名** — EV コード署名証明書の取得と署名フローの設計
- **セットアップが返すデータの最終仕様** — 現在: ユーザーネーム、言語。その他のフィールド（アバター、テーマ等）は検討中

---

## 7. 優先順位

| 優先度 | 対象 | 理由 |
|--------|------|------|
| 最優先 | Phase A（Python 梱包基盤） | 全ての後続タスクの前提。Python が動かないと何も始まらない |
| 高 | Phase B + C（並行可能） | ブートストラップと core_setup Pack は相互依存があるが並行着手可能 |
| 高 | Phase D | Rust ⇔ React ブリッジは Phase B/C 完了後すぐに着手 |
| 中 | Phase E（ユーザー担当） | UI 実装はユーザーが担当。D-2 の型定義完了後に着手可能 |
| 中 | Phase F（各 Phase と並行） | テストは各 Phase の実装と並行して作成可能 |
| 最後 | Tauri 統合 | Phase A〜D の基盤が全て揃ってから統合する |
