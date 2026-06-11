<!-- docs-i18n-links:start -->
[EN](../../../../examples/desktop_app_pack/README.md) | [JP](./README.md) | [KR](../../../ko/examples/desktop_app_pack/README.md) | [CN](../../../zh-cn/examples/desktop_app_pack/README.md)
<!-- docs-i18n-links:end -->

# デスクトップアプリパック

これは、Rumi AI OS の **desktop_app.execute** 機能を使用するサンプル パックです。
別のデスクトップ ウィンドウ (tkinter) でアプリを起動します。

Pack は、開発者がコピーして変更できるテンプレートとしても機能します。

---

## ディレクトリ構造

```
desktop_app_pack/
├── ecosystem.json   # Pack マニフェスト（desktop_app セクション付き）
├── app.py           # デスクトップアプリ（tkinter Hello World + Kernel API 通信）
└── README.md        # このファイル
```

---

## desktop_app.execute 機能とは何ですか?

`desktop_app.execute` は、Pack が **独立したデスクトップ ウィンドウ** でアプリケーションを起動できるようにする Rumi AI OS の中核機能です。

ビューア内のフロントエンド表示 (`viewer:display`) とは異なります。

1. `pack-shell` バイナリによりカーネル起動確認とトークン取得を自動化
2. 環境変数 (`RUMI_TOKEN`、`RUMI_PORT`、`RUMI_PACK_ID`) を介してカーネル API と通信します。
3. tkinter、Qt、Electron、Tauri などの任意の GUI フレームワークを使用できます。

能力の定義は`core_runtime/core_pack/core_desktop_capability/`にあります。

---

## 使い方

### 1. パックシェルを構築する

```bash
cd pack-shell
cargo build --release
```

### 2. パックを置きます

このディレクトリを `ecosystem/` にコピーします。

```bash
cp -r docs/examples/desktop_app_pack/ ecosystem/desktop_app_pack/
```

### 3. カーネルの起動

```bash
python -m rumi_ai
```

カーネルが起動すると、`ecosystem/desktop_app_pack/ecosystem.json` が自動的にスキャンされます。

### 4. パックを承認する

エコシステム パックは初回に承認が必要です (core_packs とは異なり、自動的に承認されません)。
カーネルAPIまたは管理画面からパックの承認を行ってください。

### 5. 助成金を獲得する

`desktop_app.execute` 許可の付与が必要です。
**注意**: `desktop_app.execute` は `dangerous: true` に設定されます。承認の付与とは、デスクトップ アプリがホスト OS 上で任意のプロセスを起動するための許可を意味します。

### 6. Pack-Shell でアプリを起動します

```bash
pack-shell run desktop_app_pack \
  --command "python app.py" \
  --working-dir /path/to/desktop_app_pack \
  --api-token "$RUMI_API_TOKEN"
```

tkinter ウィンドウが開き、カーネル API とヘルス チェック機能への接続情報が表示されます。

---

## エコシステム.jsonの説明

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

|フィールド |説明 |
|-----------|------|
| `desktop_app.command` | Pack-Shell が起動するコマンド。 `--command` 引数として渡される |
| `desktop_app.requires_api_token` | `DesktopAppManager`は必須の`RUMI_API_TOKEN`として扱われますか?現在の状態は常に `true` に保存されます。
| `desktop_app.window.title` |ショートカット名/ウィンドウのタイトルに使用 |
| `desktop_app.window.width/height` |推奨ウィンドウサイズ（アプリ側で閲覧する場合） |
| `desktop_app.platforms` |サポートされているプラ​​ットフォーム |

---

## カーネル API 通信

`app.py` には、カーネル API へのサンプル通信が含まれています。

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

Pack-Shell によって設定される環境変数:

|変数 |説明 |
|------|------|
| `RUMI_TOKEN` |カーネルによって発行された一時トークン |
| `RUMI_PORT` |カーネル API ポート番号 (デフォルト: 8765) |
| `RUMI_PACK_ID` |ターゲット パック ID |

---

## カスタマイズのヒント

- **GUI の変更**: `app.py` の tkinter コードは、Qt、wxPython、Electron などに置き換えることができます。
- **API 呼び出しを追加**: `Authorization: Bearer` ヘッダーに `RUMI_TOKEN` を設定することで、カーネル API を呼び出すことができます。
- **コマンド変更**: `ecosystem.json`の`desktop_app.command`を`"node app.js"`または`"./my_binary"`に変更できます。
- **トークン コントラクト**: `DesktopAppManager` によるアクティベーションの前に、`RUMI_API_TOKEN` が必要です。
- **パック名の変更**: `ecosystem.json`の`pack_id`と`pack_identity`を変更してください。
- **ウィンドウ設定**: `title`、`width`、`height`、`desktop_app.window`を変更できます。

---

## 関連ドキュメント

- [パックデスクトップアプリ開発ガイド](../../pack_desktop_app_guide.md)
- [パック開発ガイド](../../pack-development.md)
- [多言語パック開発ガイド](../../multilang_pack_guide.md)
- [パックシェルのREADME](../../../../../../pack-shell/i18n/ja/README.md)
