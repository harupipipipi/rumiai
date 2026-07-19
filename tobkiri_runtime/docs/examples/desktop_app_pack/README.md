# Desktop App Pack

Rumi AI OS の **desktop_app.execute** capability を使うサンプル Pack です。
独立したデスクトップウィンドウ（tkinter）でアプリを起動します。

Pack 開発者がコピーして改造できるテンプレートとしても機能します。

---

## ディレクトリ構成

```
desktop_app_pack/
├── ecosystem.json   # Pack マニフェスト（desktop_app セクション付き）
├── app.py           # デスクトップアプリ（tkinter Hello World + Kernel API 通信）
└── README.md        # このファイル
```

---

## desktop_app.execute capability とは

`desktop_app.execute` は Rumi AI OS の core capability の一つで、Pack が **独立したデスクトップウィンドウ** でアプリケーションを起動するための権限です。

Viewer 内のフロントエンド表示（`viewer:display`）とは異なり:

1. `pack-shell` バイナリが Kernel の起動確認・トークン取得を自動化
2. 環境変数 (`RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID`) を通じて Kernel API と通信
3. tkinter, Qt, Electron, Tauri など任意の GUI フレームワークが使用可能

capability の定義は `core_runtime/core_pack/core_desktop_capability/` にあります。

---

## 使い方

### 1. pack-shell をビルドする

```bash
cd pack-shell
cargo build --release
```

### 2. Pack を配置する

このディレクトリを `ecosystem/` にコピーします:

```bash
cp -r docs/examples/desktop_app_pack/ ecosystem/desktop_app_pack/
```

### 3. Kernel を起動する

```bash
python -m tobkiri
```

Kernel が起動すると `ecosystem/desktop_app_pack/ecosystem.json` を自動でスキャンします。

### 4. Pack を承認する

ecosystem Pack は初回で承認が必要です（core_pack と異なり自動承認されません）。
Kernel の API または管理画面から Pack を承認してください。

### 5. Grant を取得する

`desktop_app.execute` permission の Grant が必要です。
**注意**: `desktop_app.execute` は `dangerous: true` に設定されています。Grant の承認はデスクトップアプリがホスト OS 上で任意のプロセスを起動する許可を意味します。

### 6. pack-shell でアプリを起動する

```bash
pack-shell run desktop_app_pack \
  --command "python app.py" \
  --working-dir /path/to/desktop_app_pack \
  --api-token "$RUMI_API_TOKEN"
```

tkinter ウィンドウが開き、Kernel API への接続情報と Health Check 機能が表示されます。

---

## ecosystem.json の解説

```json
{
  "pack_id": "desktop_app_pack",
  "desktop_app": {
    "command": "python app.py",
    "window": {
      "title": "Desktop App Pack",
      "width": 600,
      "height": 400
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

| フィールド | 説明 |
|-----------|------|
| `desktop_app.command` | pack-shell が起動するコマンド。`--command` 引数として渡される |
| `desktop_app.requires_api_token` | `DesktopAppManager` が `RUMI_API_TOKEN` 必須として扱うか。現状は常に `true` で保存される |
| `desktop_app.window.title` | ショートカット名・ウィンドウタイトルに使用される |
| `desktop_app.window.width/height` | ウィンドウの推奨サイズ（アプリ側で読み取る場合） |
| `desktop_app.platforms` | サポートするプラットフォーム |

---

## Kernel API 通信

`app.py` に Kernel API への通信サンプルが含まれています。

```python
import json
from urllib.request import Request, urlopen

port = os.environ.get("RUMI_PORT", "8765")
url = f"http://127.0.0.1:{port}/health"
req = Request(url, headers={"Accept": "application/json"})
with urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(data)  # {"status": "ok"}
```

pack-shell が設定する環境変数:

| 変数 | 説明 |
|------|------|
| `RUMI_TOKEN` | Kernel が発行した一時トークン |
| `RUMI_PORT` | Kernel API のポート番号（デフォルト: 8765） |
| `RUMI_PACK_ID` | 対象 Pack の ID |

---

## カスタマイズのヒント

- **GUI を変更する**: `app.py` の tkinter コードを Qt, wxPython, Electron 等に置き換えられます
- **API 呼び出しを追加する**: `RUMI_TOKEN` を `Authorization: Bearer` ヘッダーに設定して Kernel API を呼び出せます
- **command を変更する**: `ecosystem.json` の `desktop_app.command` を `"node app.js"` や `"./my_binary"` に変更できます
- **token 契約**: `DesktopAppManager` 経由の起動では `RUMI_API_TOKEN` が事前に必要です
- **Pack 名を変更する**: `ecosystem.json` の `pack_id` と `pack_identity` を変更してください
- **ウィンドウ設定**: `desktop_app.window` の `title`, `width`, `height` を変更できます

---

## 関連ドキュメント

- [Pack デスクトップアプリ開発ガイド](../../pack_desktop_app_guide.md)
- [Pack 開発ガイド](../../pack-development.md)
- [多言語 Pack 開発ガイド](../../multilang_pack_guide.md)
- [pack-shell README](../../../../pack-shell/README.md)
