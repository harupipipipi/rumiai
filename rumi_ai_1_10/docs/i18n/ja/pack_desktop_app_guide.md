<!-- docs-i18n-links:start -->
[EN](../../pack_desktop_app_guide.md) | [JP](./pack_desktop_app_guide.md) | [KR](../ko/pack_desktop_app_guide.md) | [CN](../zh-cn/pack_desktop_app_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — パックデスクトップアプリ開発ガイド

最終更新日: 2026-03-28

このドキュメントは、**デスクトップ アプリ** (別のデスクトップ ウィンドウで実行されるアプリケーション) を Rumi AI OS パックに統合するための開発者向けのガイドです。 Ecosystem.json のセットアップ方法、パックシェル バイナリの使用方法、セキュリティ モデル、ショートカットの生成について説明します。

---

## 1. デスクトップ アプリ パックとは何ですか?

### 1.1 概要

Pack デスクトップ アプリを使用すると、Rumi AI OS の **機能ベースの権限システム** を通じて、アプリケーションを別のデスクトップ ウィンドウで実行できます。

Rumi Viewer (Tauri ベースの WebView UI) 内にフロントエンドを表示する `viewer:display` 機能とは異なり、`desktop_app.execute` 機能は **OS ネイティブ ウィンドウ**でアプリを起動します。 tkinter、Qt、Electron、Tauri などの GUI フレームワークを使用できます。

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

### 1.3 えこひいきの禁止の原則

デスクトップ アプリのサポートも、他の機能と同じパターンを使用して実装されます。 `core_desktop_capability` は core_pack としてカーネルに含まれており、`desktop_app.execute` の権限を管理します。他の機能と同様に、サードパーティのパックでもこの機能を使用するには許可が必要です。

---

## 2. 前提条件

デスクトップ アプリ パックを開発して実行するには、次のものが必要です。

- **Rumi AI OS**がインストールおよび起動できる環境
- **pack-shell バイナリ** がビルドされました (以下のビルド手順を参照)
- **Python 3.11 以降** (サンプル アプリの場合。アプリ自体は任意の言語で実装できます)

---

## 3.エコシステム.jsonのdesktop_appセクション

デスクトップ アプリの機能をパックに追加するには、`desktop_app` セクションを `ecosystem.json` に追加します。

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

### 3.2 フィールドリスト

|フィールド |タイプ |必須 |説明 |
|-----------|-----|------|------|
| `command` |文字列 | ✅ |コマンドを開始します。 Pack-Shell | の `--command` 引数としてアプリに渡されます。
| `working_dir` |文字列 | — |アプリの作業ディレクトリ。空の文字列の場合、Pack ディレクトリが使用されます。
| `env` |辞書 | — |アプリに渡す追加の環境変数。 `RUMI_TOKEN`、`RUMI_PORT`、`RUMI_PACK_ID` は、pack-shell が自動的に設定するため必要ありません。
| `capabilities` |リスト | — |要求された機能のリスト |
| `window` |辞書 | — |ウィンドウの設定。 `title`(string)でアプリ名を指定し、`width`/`height`(int)でサイズを指定します。ショートカット名にも使用されます |
| `platforms` |リスト | — |サポートされているプラ​​ットフォーム。 `"darwin"`、`"win32"`、`"linux"`の組み合わせ |

### 3.3 スキーマの検証

カーネルの `PackImporter` は、次のルールに従って `desktop_app` セクションを検証します。

- `desktop_app` が存在する場合、それは辞書でなければなりません
- `desktop_app.command` は必須であり、空ではない文字列である必要があります
- `working_dir`は文字列、`env`は辞書、`capabilities`はリスト、`window`は辞書、`platforms`はリストである必要があります(すべて省略可能)

検証が失敗した場合、パックのインポート時に警告が出力され、パックは登録されません。

---

## 4.desktop_app.execute 機能

### 4.1 概要

`desktop_app.execute` は、`core_desktop_capability` Pack によって提供される機能です。デスクトップ アプリの起動、停止、ステータスの確認を制御します。

### 4.2 マニフェスト.json

```json
{
  "function_id": "execute",
  "description": "デスクトップアプリケーションを起動・管理する",
  "requires": ["desktop_app.execute"],
  "grant_config": {
    "permission_id": "desktop_app.execute",
    "dangerous": true,
    "allowed_packs": ["my_desktop_pack"],
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

### 4.3 危険フラグ

`desktop_app.execute`は`dangerous: true`に設定されます。これは、デスクトップ アプリがホスト OS 上で任意のプロセスを起動するため、高い権限を持っていることを意味します。 Docker で分離された Python 関数とは異なり、デスクトップ アプリはホストのファイル システムとネットワークに直接アクセスできます。

したがって、ユーザーはパックをインストールするときに `desktop_app.execute` 付与を明示的に承認する必要があります。

### 4.4 アクション

|アクション |説明 |
|--------|------|
| `launch` |アプリを起動してトークンを発行します (デフォルト) |
| `stop` |実行中のアプリを停止する |
| `status` |アプリの実行ステータスを返します |

---

## 5. パックシェルの使用方法

### 5.1 ビルド

```bash
cd pack-shell
cargo build --release
```

ビルドアーティファクト: `target/release/pack-shell`

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

Pack-Shell にはサブコマンド `run` と `version` があります。

#### サブコマンドを実行

```
pack-shell run <PACK_ID> --command <COMMAND> [OPTIONS]
```

|引数 |タイプ |必須 |デフォルト |説明 |
|------|-----|------|-----------|------|
| `<PACK_ID>` |位置引数 | ✅ | — |起動するパックの ID |
| `--command` |文字列 | ✅ | — |実行するコマンド (例: `"python app.py"`) |
| `--api-token` |文字列 | ✅ |環境変数 `RUMI_API_TOKEN` |カーネル API 認証トークン |
| `--port` | u16 | — | `8765` |カーネル API ポート番号 |
| `--kernel-cmd` |文字列 | — | `"python -m rumi_ai"` |カーネルが起動していない場合に起動するコマンド |
| `--timeout` | u64 | — | `60` |カーネル起動待機タイムアウト (秒) |
| `--working-dir` |文字列 | — |なし |アプリの作業ディレクトリ |

#### version サブコマンド

```bash
pack-shell version
# 出力: pack-shell 0.1.0
```

### 5.3 実行例

```bash
# 基本的な使い方
pack-shell run my_desktop_pack --command "python app.py" --working-dir /path/to/my_desktop_pack --api-token "$TOKEN"

# 全オプション指定
pack-shell run my_desktop_pack \
  --command "python app.py" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai" \
  --api-token "your-api-token" \
  --timeout 60 \
  --working-dir /path/to/workdir
```

### 5.4 実行フロー

Pack-Shell は次のようにデスクトップ アプリを起動します。

1. `GET /health`でカーネルの動作状況を確認します。
2. カーネルが応答しない場合は、`--kernel-cmd` でカーネルを起動し、ヘルス チェックをポーリングします (1 秒間隔、最大 `--timeout`)。
3. `POST /api/desktop/token`で一時トークンを取得します。
4. 環境変数 `RUMI_TOKEN`、`RUMI_PORT`、`RUMI_PACK_ID` を設定し、アプリ プロセスを開始します。
5. アプリのプロセスが終了し、終了コードが返されるのを待ちます。

### 5.5 環境変数

Pack-Shell によって読み取られる環境変数:

|変数 |説明 |
|------|------|
| `RUMI_API_TOKEN` | `--api-token`の置き換え。 CLI 引数が優先されます。

`DesktopAppManager` による起動は、環境変数として `RUMI_API_TOKEN` を提供するコントラクトに固定されています。

Pack-Shell がアプリに渡す環境変数:

|変数 |説明 |
|------|------|
| `RUMI_TOKEN` |カーネルによって発行された一時トークン |
| `RUMI_PORT` |カーネル API ポート番号 |
| `RUMI_PACK_ID` |ターゲット パック ID |

---

## 6. API リファレンス

### 6.1 POST /api/desktop/token

デスクトップ アプリの一時トークンを発行します。 `core_desktop_capability` Pack が提供する API ルート。

#### リクエスト

```json
{
  "pack_id": "my_desktop_pack"
}
```

|フィールド |タイプ |必須 |説明 |
|-----------|-----|------|------|
| `pack_id` |文字列 | ✅ |トークンが発行されるパック ID |

#### 応答 (成功)

```json
{
  "token": "abc-123-xyz",
  "port": 8765,
  "expires_in": 3600
}
```

|フィールド |タイプ |説明 |
|-----------|-----|------|
| `token` |文字列 |短期アクセストークン |
| `port` |整数 |カーネル API ポート番号 (デフォルト: 8765) |
| `expires_in` |整数 |トークンの有効期限 (秒、デフォルト: 3600) |

#### 応答 (エラー)

```json
{
  "error": "desktop_app.execute not granted for pack: my_desktop_pack",
  "status_code": 403
}
```

|ステータスコード |説明 |
|------------|------|
| 400 | `pack_id` が指定されていない、または無効です |
| 403 | `desktop_app.execute` に対する助成金はありません |
| 500 |内部エラー |
| 503 |デスクトップ機能ハンドラーは使用できません |

---

## 7. ショートカットの生成

### 7.1 DesktopAppManager

`desktop_app_manager.py` の `DesktopAppManager` クラスは、Pack デスクトップ アプリのライフサイクルを管理します。

#### 主な方法

|方法 |説明 |
|--------|------|
| `register_app(pack_id, desktop_app_config, pack_dir)` | Pack デスクトップ アプリを登録し、プラットフォーム固有のショートカットを生成する |
| `unregister_app(pack_id)` |購読を解除してショートカットを削除する |
| `launch_app(pack_id)` |登録したアプリを起動する |
| `stop_app(pack_id)` | SIGTERM を使用して実行中のアプリケーションを停止する |
| `list_registered_apps()` |登録済みアプリのリストを返す |

#### register_app の戻り値

```json
{
  "success": true,
  "shortcut_path": "/Users/user/Applications/MyApp.app"
}
```

### 7.2 プラットフォームのショートカット

`register_app` は、プラットフォーム固有のショートカットを自動的に生成します。

|プラットフォーム |フォーマット |場所 |
|---------------|------|--------|
| macOS (`darwin`) | `.app` バンドル (Info.plist + 起動スクリプト) | `~/Applications/<AppName>.app` |
| Windows (`win32`) | `.lnk` ショートカット (PowerShell で生成) | `user_data/apps/<AppName>.lnk` |
|リナックス | `.desktop` ファイル | `~/.local/share/applications/rumi-<AppName>.desktop` |

ショートカット `AppName` は `desktop_app.window.title` (指定されていない場合は `pack_id`) から取得されます。

### 7.3 パックシェルバイナリの検索

`DesktopAppManager` は、次の順序でパックシェル バイナリを検索します。

1. 環境変数`RUMI_PACK_SHELL_PATH`に指定したパス
2.システム内で`PATH`から`pack-shell`を検索します。

見つからない場合、`register_app` はエラーを返します。

---

## 8. セキュリティ

### 8.1 なぜ危険なのでしょうか?

`desktop_app.execute` は、次の理由により `dangerous: true` に設定されます。

- デスクトップ アプリはホスト OS 上で直接実行されます (Docker 分離なし)
- ファイル システム、ネットワーク、その他のプロセスにアクセスできます
- `command` フィールドで指定されたコマンドが実行されます。

### 8.2 ユーザー承認の重要性

パックは悪意を持って設計されています。ユーザーは、許可を承認する前に、デスクトップ アプリ `command` が起動するプログラムを必ず確認する必要があります。

### 8.3 トークンの有効期限

`POST /api/desktop/token` で発行されたトークンは、短期間 (デフォルトは 3600 秒 = 1 時間) で期限切れになります。 `max_token_lifetime`は`grant_config`によって制御されます。

`allowed_packs` はフェールクローズされています。空の配列 `[]`、未指定、または不正な型は、どのパックでも許可されません。すべてのパックを明示的に許可する必要がある検証目的で `["*"]` を指定できますが、一般的には、起動するパック ID をリストする必要があります。

### 8.4 推奨事項

- 信頼できるソースからのみパックをインストールしてください
- 助成金を承認する前に`desktop_app.command`の内容を確認してください
- 不要になったパックについては、`unregister_app` でショートカットを削除してください。
- `allowed_packs`を設定して、特定のパックにのみ許可を許可します

---

## 9. 開発の流れ

### 9.1 ステップバイステップ

1. **アプリの開発**: tkinter、Qt、Electron などのフレームワークを使用してデスクトップ アプリを作成します。
2. **環境変数のサポート**: `RUMI_TOKEN`、`RUMI_PORT`、`RUMI_PACK_ID`を読み取り、アプリ内のカーネル API と通信するコードを実装します。
3. **pack-shell でテスト**: `pack-shell run <PACK_ID> --command "python app.py" --working-dir <DIR> --api-token <TOKEN>` で動作を確認します。
4. **desktop_appをecosystem.jsonに追加**: `command`、`window`、`platforms`などを設定します。
5. **Pack をインストールします**: `ecosystem/` に配置するか、PackImporter を使用してインポートします。
6. **許可の承認**: GrantManager で `desktop_app.execute` の許可を設定します。
7. **ショートカットの生成**: DesktopAppManager の `register_app` を使用して、プラットフォーム固有のショートカットを自動的に生成します。

### 9.2 ローカル開発のヒント

環境変数を手動で設定し、pack-shell を使用せずにアプリを直接起動することもできます。

```bash
export RUMI_TOKEN="dev-token-for-testing"
export RUMI_PORT="8765"
export RUMI_PACK_ID="my_desktop_pack"
python app.py
```

カーネルが実行されたら、`GET /health` を使用して接続を確認できます。

```bash
curl http://localhost:8765/health
# {"status": "ok"}
```

---

## 10. トラブルシューティング

### パックシェルがカーネルに接続できません

- カーネルが実行されているかどうかを確認します: `curl http://localhost:8765/health`
- ポート番号が正しいかどうかを確認します。デフォルトは`8765`です。
- `--kernel-cmd`で正しいカーネル起動コマンドが指定されているか確認してください。

### トークン取得時の 403 エラー

- `desktop_app.execute`のGrantが設定されているか確認してください。
- `pack_id`が正しいか確認してください
- APIトークン(`--api-token`または`RUMI_API_TOKEN`)が有効かどうかを確認します

### ショートカットは生成されませんでした

- パックシェルバイナリが見つかったかどうかを確認します。`RUMI_PACK_SHELL_PATH` を設定するか、`PATH` に追加します。
- `register_app`の戻り値を確認してください: `{"success": false, "error": "..."}`にはエラーメッセージが含まれています

### アプリが起動しない

- `desktop_app.command` が正しいコマンドかどうかを確認します。シェルで直接実行してみてください。
- `working_dir` が正しいディレクトリを指していることを確認してください
- 必要な依存ライブラリがインストールされているかどうかを確認します

### macOS で .app を開けません

- ゲートキーパーによってブロックされている場合: 「システム環境設定 > セキュリティとプライバシー」から許可します。
- 起動スクリプトに実行権限があるか確認します: `chmod +x ~/Applications/MyApp.app/Contents/MacOS/launch`

---

## 関連ドキュメント

- [パック開発ガイド](./pack-development.md) — パックの概要
- [多言語パック開発ガイド](./multilang_pack_guide.md) — Python 以外の言語でパックを開発する方法
- [サンプルコード: デスクトップ アプリ パック](examples/desktop_app_pack/) — デスクトップ アプリ パックのテンプレート
- [pack-shell README](../../../../pack-shell/i18n/ja/README.md) — パックシェルのバイナリの詳細
