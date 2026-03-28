# Rumi AI OS — Pack デスクトップアプリ開発ガイド

最終更新: 2026-03-28

本ドキュメントは Rumi AI OS の Pack に **デスクトップアプリ**（独立したデスクトップウィンドウで動作するアプリケーション）を組み込むための開発者向けガイドです。ecosystem.json の設定方法、pack-shell バイナリの使い方、セキュリティモデル、ショートカット生成までを網羅します。

---

## 1. デスクトップアプリ Pack とは

### 1.1 概要

Pack デスクトップアプリは、Rumi AI OS の **capability ベースの権限システム** を通じて、独立したデスクトップウィンドウでアプリケーションを動作させる仕組みです。

Rumi Viewer（Tauri ベースの WebView UI）内にフロントエンドを表示する `viewer:display` capability とは異なり、`desktop_app:execute` capability は **OS ネイティブのウィンドウ** でアプリを起動します。tkinter, Qt, Electron, Tauri など任意のGUIフレームワークが使えます。

### 1.2 アーキテクチャ

```
ユーザー
  │
  ├── ショートカット / CLI
  │       │
  │       ▼
  │   pack-shell (Rust バイナリ)
  │       │
  │       ├─ 1. Kernel /health チェック
  │       ├─ 2. Kernel 未起動なら自動起動
  │       ├─ 3. POST /api/desktop/token でトークン取得
  │       ├─ 4. 環境変数 (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID) を設定
  │       └─ 5. アプリプロセスを起動
  │               │
  │               ▼
  │           デスクトップアプリ (Python, Node.js, etc.)
  │               │
  │               ▼
  │           Kernel API (localhost:8765) と通信
  │
  └── Rumi AI OS Kernel
          │
          ├── CapabilityGrantManager (Grant 検証)
          ├── DesktopAppManager (登録・ショートカット生成)
          └── POST /api/desktop/token (トークン発行)
```

### 1.3 No Favoritism 原則

デスクトップアプリ対応も他の capability と同じパターンで実装されています。`core_desktop_capability` は core_pack として Kernel に同梱されており、`desktop_app.execute` permission を管理します。サードパーティ Pack がこの capability を使うには、他の capability と同様に Grant（認可）が必要です。

---

## 2. 前提条件

デスクトップアプリ Pack を開発・実行するには、以下が必要です:

- **Rumi AI OS** がインストール・起動可能な環境
- **pack-shell バイナリ** がビルド済みであること（後述のビルド手順を参照）
- **Python 3.11 以上**（サンプルアプリの場合。アプリ自体は任意の言語で実装可能）

---

## 3. ecosystem.json の desktop_app セクション

Pack にデスクトップアプリ機能を追加するには、`ecosystem.json` に `desktop_app` セクションを追加します。

### 3.1 設定例

```json
{
  "pack_id": "my_desktop_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Desktop App",
    "description": "デスクトップアプリのサンプル Pack"
  },
  "desktop_app": {
    "command": "python app.py",
    "working_dir": "",
    "env": {},
    "capabilities": ["desktop_app.execute"],
    "window": {
      "title": "My Desktop App",
      "width": 800,
      "height": 600
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

### 3.2 フィールド一覧

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `command` | string | ✅ | 起動コマンド。pack-shell の `--command` 引数としてアプリに渡される |
| `working_dir` | string | — | アプリの作業ディレクトリ。空文字列の場合は Pack ディレクトリが使用される |
| `env` | dict | — | アプリに追加で渡す環境変数。`RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID` は pack-shell が自動設定するため不要 |
| `capabilities` | list | — | 要求する capability のリスト |
| `window` | dict | — | ウィンドウ設定。`title`（string）でアプリ名、`width`/`height`（int）でサイズを指定。ショートカット名にも使用される |
| `platforms` | list | — | サポートするプラットフォーム。`"darwin"`, `"win32"`, `"linux"` の組み合わせ |

### 3.3 スキーマ検証

Kernel の `PackImporter` は `desktop_app` セクションを以下のルールで検証します:

- `desktop_app` が存在する場合、dict でなければならない
- `desktop_app.command` は必須で、空でない文字列でなければならない
- `working_dir` は string、`env` は dict、`capabilities` は list、`window` は dict、`platforms` は list でなければならない（いずれも省略可能）

検証に失敗すると、Pack のインポート時に警告が出力され、Pack は登録されません。

---

## 4. desktop_app:execute capability

### 4.1 概要

`desktop_app:execute` は `core_desktop_capability` Pack が提供する capability です。デスクトップアプリの起動・停止・ステータス確認を制御します。

### 4.2 manifest.json

```json
{
  "function_id": "execute",
  "description": "デスクトップアプリケーションを起動・管理する",
  "requires": ["desktop_app.execute"],
  "grant_config": {
    "permission_id": "desktop_app:execute",
    "dangerous": true,
    "allowed_packs": [],
    "max_token_lifetime": 3600
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "pack_id": {
        "type": "string",
        "description": "Pack ID whose desktop app to execute"
      },
      "action": {
        "type": "string",
        "description": "Action to perform: launch, stop, status",
        "default": "launch",
        "enum": ["launch", "stop", "status"]
      }
    },
    "required": ["pack_id"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "token": { "type": "string" },
      "port": { "type": "integer" },
      "expires_in": { "type": "integer" }
    },
    "required": ["token", "port", "expires_in"]
  },
  "calling_convention": "block"
}
```

### 4.3 dangerous フラグ

`desktop_app:execute` は `dangerous: true` に設定されています。これは、デスクトップアプリがホスト OS 上で **任意のプロセスを起動する** ため、高い権限を持つことを意味します。Docker 隔離された Python Function とは異なり、デスクトップアプリはホストのファイルシステムやネットワークに直接アクセスできます。

そのため、ユーザーは Pack をインストールする際に、`desktop_app:execute` の Grant を明示的に承認する必要があります。

### 4.4 action

| action | 説明 |
|--------|------|
| `launch` | アプリを起動し、トークンを発行する（デフォルト） |
| `stop` | 起動中のアプリを停止する |
| `status` | アプリの実行状態を返す |

---

## 5. pack-shell の使い方

### 5.1 ビルド

```bash
cd pack-shell
cargo build --release
```

ビルド成果物: `target/release/pack-shell`

クロスコンパイル:

```bash
# macOS (Apple Silicon)
cargo build --release --target aarch64-apple-darwin

# macOS (Intel)
cargo build --release --target x86_64-apple-darwin

# Windows
cargo build --release --target x86_64-pc-windows-msvc

# Linux
cargo build --release --target x86_64-unknown-linux-gnu
```

### 5.2 CLI リファレンス

pack-shell にはサブコマンド `run` と `version` があります。

#### run サブコマンド

```
pack-shell run <PACK_ID> --command <COMMAND> --api-token <TOKEN> [OPTIONS]
```

| 引数 | 型 | 必須 | デフォルト | 説明 |
|------|-----|------|-----------|------|
| `<PACK_ID>` | 位置引数 | ✅ | — | 起動する Pack の ID |
| `--command` | string | ✅ | — | 実行するコマンド（例: `"python app.py"`） |
| `--api-token` | string | ✅ | 環境変数 `RUMI_API_TOKEN` | Kernel API の認証トークン |
| `--port` | u16 | — | `8765` | Kernel API のポート番号 |
| `--kernel-cmd` | string | — | `"python -m rumi_ai_1_10"` | Kernel が未起動の場合に起動するコマンド |
| `--timeout` | u64 | — | `60` | Kernel 起動待ちのタイムアウト（秒） |
| `--working-dir` | string | — | なし | アプリの作業ディレクトリ |

#### version サブコマンド

```bash
pack-shell version
# 出力: pack-shell 0.1.0
```

### 5.3 実行例

```bash
# 基本的な使い方
pack-shell run my_desktop_pack --command "python app.py" --api-token "$TOKEN"

# 全オプション指定
pack-shell run my_desktop_pack \
  --command "python app.py" \
  --api-token "your-api-token" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai_1_10" \
  --timeout 60 \
  --working-dir /path/to/workdir
```

### 5.4 実行フロー

pack-shell は以下の手順でデスクトップアプリを起動します:

1. `GET /health` で Kernel の稼働状態を確認
2. Kernel が応答しない場合、`--kernel-cmd` でカーネルを起動し、ヘルスチェックをポーリング（1秒間隔、`--timeout` まで）
3. `POST /api/desktop/token` で一時トークンを取得
4. 環境変数 `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID` を設定してアプリプロセスを起動
5. アプリプロセスの終了を待ち、exit code を返す

### 5.5 環境変数

pack-shell が読む環境変数:

| 変数 | 説明 |
|------|------|
| `RUMI_API_TOKEN` | `--api-token` の代替。CLI 引数が優先される |

pack-shell がアプリに渡す環境変数:

| 変数 | 説明 |
|------|------|
| `RUMI_TOKEN` | Kernel が発行した一時トークン |
| `RUMI_PORT` | Kernel API のポート番号 |
| `RUMI_PACK_ID` | 対象 Pack の ID |

---

## 6. API リファレンス

### 6.1 POST /api/desktop/token

デスクトップアプリ用の一時トークンを発行します。`core_desktop_capability` Pack が提供する API ルートです。

#### リクエスト

```json
{
  "pack_id": "my_desktop_pack"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `pack_id` | string | ✅ | トークンを発行する対象の Pack ID |

#### レスポンス（成功）

```json
{
  "token": "abc-123-xyz",
  "port": 8765,
  "expires_in": 3600
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `token` | string | 短期アクセストークン |
| `port` | integer | Kernel API のポート番号（デフォルト: 8765） |
| `expires_in` | integer | トークンの有効期限（秒。デフォルト: 3600） |

#### レスポンス（エラー）

```json
{
  "error": "desktop_app.execute not granted for pack: my_desktop_pack",
  "status_code": 403
}
```

| status_code | 説明 |
|------------|------|
| 400 | `pack_id` が未指定または無効 |
| 403 | `desktop_app.execute` の Grant がない |
| 500 | 内部エラー |
| 503 | Desktop capability handler が利用不可 |

---

## 7. ショートカット生成

### 7.1 DesktopAppManager

`desktop_app_manager.py` の `DesktopAppManager` クラスが Pack デスクトップアプリのライフサイクルを管理します。

#### 主要メソッド

| メソッド | 説明 |
|--------|------|
| `register_app(pack_id, desktop_app_config, pack_dir)` | Pack のデスクトップアプリを登録し、プラットフォーム別ショートカットを生成する |
| `unregister_app(pack_id)` | 登録を解除し、ショートカットを削除する |
| `launch_app(pack_id)` | 登録済みアプリを起動する |
| `stop_app(pack_id)` | 起動中のアプリを SIGTERM で停止する |
| `list_registered_apps()` | 登録済みアプリの一覧を返す |

#### register_app の戻り値

```json
{
  "success": true,
  "shortcut_path": "/Users/user/Applications/MyApp.app"
}
```

### 7.2 プラットフォーム別ショートカット

`register_app` はプラットフォームに応じたショートカットを自動生成します:

| プラットフォーム | 形式 | 配置先 |
|---------------|------|--------|
| macOS (`darwin`) | `.app` bundle（Info.plist + launch スクリプト） | `~/Applications/<AppName>.app` |
| Windows (`win32`) | `.lnk` ショートカット（PowerShell で生成） | `user_data/apps/<AppName>.lnk` |
| Linux | `.desktop` ファイル | `~/.local/share/applications/rumi-<AppName>.desktop` |

ショートカットの `AppName` は `desktop_app.window.title` から取得されます（未指定の場合は `pack_id`）。

### 7.3 pack-shell バイナリの検索

`DesktopAppManager` は以下の順で pack-shell バイナリを検索します:

1. 環境変数 `RUMI_PACK_SHELL_PATH` に指定されたパス
2. システムの `PATH` から `pack-shell` を検索

見つからない場合、`register_app` はエラーを返します。

---

## 8. セキュリティ

### 8.1 なぜ dangerous なのか

`desktop_app:execute` は以下の理由で `dangerous: true` に設定されています:

- デスクトップアプリは **ホスト OS 上で直接実行される**（Docker 隔離なし）
- ファイルシステム、ネットワーク、他のプロセスへのアクセスが可能
- `command` フィールドに指定された任意のコマンドが実行される

### 8.2 ユーザー承認の重要性

Pack は悪意前提で設計されています。デスクトップアプリの `command` がどのようなプログラムを起動するか、ユーザーは必ず確認してから Grant を承認してください。

### 8.3 トークンの有効期限

`POST /api/desktop/token` で発行されるトークンは短期間（デフォルト 3600 秒 = 1 時間）で失効します。`max_token_lifetime` は `grant_config` で制御されます。

### 8.4 推奨事項

- 信頼できるソースからの Pack のみインストールする
- `desktop_app.command` の内容を確認してから Grant を承認する
- 不要になった Pack は `unregister_app` でショートカットを削除する
- `allowed_packs` を設定して、特定の Pack にのみ Grant を許可する

---

## 9. 開発フロー

### 9.1 ステップバイステップ

1. **アプリを開発する**: tkinter, Qt, Electron など任意のフレームワークでデスクトップアプリを作成
2. **環境変数に対応する**: アプリ内で `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID` を読み取り、Kernel API と通信するコードを実装
3. **pack-shell でテストする**: `pack-shell run <PACK_ID> --command "python app.py" --api-token <TOKEN>` で動作確認
4. **ecosystem.json に desktop_app を追加する**: `command`, `window`, `platforms` 等を設定
5. **Pack をインストールする**: `ecosystem_packs/` に配置するか、PackImporter でインポート
6. **Grant を承認する**: GrantManager で `desktop_app.execute` の Grant を設定
7. **ショートカットを生成する**: DesktopAppManager の `register_app` でプラットフォーム別ショートカットを自動生成

### 9.2 ローカル開発のヒント

pack-shell を使わずに、環境変数を手動で設定してアプリを直接起動することもできます:

```bash
export RUMI_TOKEN="dev-token-for-testing"
export RUMI_PORT="8765"
export RUMI_PACK_ID="my_desktop_pack"
python app.py
```

Kernel が起動していれば `GET /health` で接続を確認できます:

```bash
curl http://localhost:8765/health
# {"status": "ok"}
```

---

## 10. トラブルシューティング

### pack-shell が Kernel に接続できない

- Kernel が起動しているか確認: `curl http://localhost:8765/health`
- ポート番号が正しいか確認: デフォルトは `8765`
- `--kernel-cmd` で正しい Kernel 起動コマンドが指定されているか確認

### トークン取得で 403 エラー

- `desktop_app.execute` の Grant が設定されているか確認
- `pack_id` が正しいか確認
- API トークン（`--api-token` または `RUMI_API_TOKEN`）が有効か確認

### ショートカットが生成されない

- pack-shell バイナリが見つかるか確認: `RUMI_PACK_SHELL_PATH` を設定するか、`PATH` に追加
- `register_app` の戻り値を確認: `{"success": false, "error": "..."}` にエラーメッセージが含まれる

### アプリが起動しない

- `desktop_app.command` が正しいコマンドか確認: シェルで直接実行してみる
- `working_dir` が正しいディレクトリを指しているか確認
- 必要な依存ライブラリがインストールされているか確認

### macOS で .app が開けない

- ゲートキーパーにブロックされている場合: 「システム環境設定 > セキュリティとプライバシー」から許可
- launch スクリプトに実行権限があるか確認: `chmod +x ~/Applications/MyApp.app/Contents/MacOS/launch`

---

## 関連ドキュメント

- [Pack 開発ガイド](pack_development_guide.md) — Pack の全体像
- [多言語 Pack 開発ガイド](multilang_pack_guide.md) — Python 以外の言語で Pack を開発する方法
- [サンプルコード: Desktop App Pack](examples/desktop_app_pack/) — デスクトップアプリ Pack のテンプレート
- [pack-shell README](../../pack-shell/README.md) — pack-shell バイナリの詳細
