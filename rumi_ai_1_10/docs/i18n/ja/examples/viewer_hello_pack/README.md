<!-- docs-i18n-links:start -->
[EN](../../../../examples/viewer_hello_pack/README.md) | [JP](./README.md) | [KR](../../../ko/examples/viewer_hello_pack/README.md) | [CN](../../../zh-cn/examples/viewer_hello_pack/README.md)
<!-- docs-i18n-links:end -->

# ビューアハローパック

これは、Rumi AI OS の **viewer:display** 機能を使用するサンプル パックです。
Rumi Viewer 内で Hello World フロントエンドを表示します。

Pack は、開発者がコピーして変更できるテンプレートとしても機能します。

---

## ディレクトリ構造

```
viewer_hello_pack/
├── ecosystem.json   # Pack マニフェスト
├── web/
│   ├── index.html   # フロントエンド（Hello World ページ）
│   └── app.js       # Kernel API 通信サンプル
└── README.md        # このファイル
```

---

## ビューア:表示機能とは何ですか?

`viewer:display` は、Rumi AI OS のコア機能の 1 つであり、Rumi Viewer (Tauri ベースのデスクトップ UI) でフロントエンドを表示するための Pack の権限です。

この機能を備えたパック:

1. `web_mount`で指定したディレクトリ内の静的ファイルがビューアから配信されます。
2. カーネルが短期トークンを発行し、ビューアがそのトークンを使用して認証します
3. フロントエンドからカーネルAPI(`localhost:8765`)を呼び出すことが可能

能力の定義は`core_runtime/core_pack/core_viewer_capability/`にあります。

---

## 使い方

### 1. パックを置きます

このディレクトリを `ecosystem/` にコピーします。

```bash
cp -r docs/examples/viewer_hello_pack/ ecosystem/viewer_hello_pack/
```

### 2. カーネルの起動

```bash
python -m rumi_ai
```

カーネルが起動すると、`ecosystem/viewer_hello_pack/ecosystem.json` が自動的にスキャンされます。

### 3. パックを承認する

エコシステム パックは初回に承認が必要です (core_packs とは異なり、自動的に承認されません)。
カーネルAPIまたは管理画面からパックの承認を行ってください。

### 4. 助成金を獲得する

`viewer.display` 許可の付与が必要です。
次のように許可を構成します。

- `viewer.display` Grant から `viewer_hello_pack` をカーネル GrantManager に追加しました
- 許可が設定されると、viewer:display 関数を通じてフロントエンドが表示されるようになります。

### 5. ビューアで表示する

Rumi Viewer を起動すると、承認/付与されたパックのフロントエンドが表示されます。
`web/index.html` がビューアに表示され、カーネル API との通信デモが動作します。

---

## エコシステム.jsonの説明

```json
{
  "pack_id": "viewer_hello_pack",
  "capabilities": ["viewer.display"],
  "web_mount": "web"
}
```

|フィールド |説明 |
|-----------|------|
| `capabilities` |要求された機能のリスト。 `viewer.display`を指定するとビューワ表示が可能になります。
| `web_mount` |静的ファイルを提供するディレクトリ。パックルートに対する相対パス |

---

## カーネル API 通信

`web/app.js` には、カーネル API へのフェッチ サンプルが含まれています。

```javascript
fetch("http://localhost:8765/api/health", {
  method: "GET",
  headers: { "Accept": "application/json" }
})
  .then(response => response.json())
  .then(data => console.log(data));
```

カーネル API のデフォルトのポートは `8765` です。

---

## カスタマイズのヒント

- **UI変更**: `web/index.html`のHTML/CSSを編集します。外部CSSフレームワークを追加することも可能
- **API 呼び出しの追加**: 新しいフェッチ呼び出しを `web/app.js` に追加します。
- **関数の追加**: `ecosystem.json` の `functions` セクションと `functions/` ディレクトリに関数を追加することで、バックエンド処理を実装することもできます。
- **複数ページ**: `web/` ディレクトリにページを追加し、SPA ルーティングと複数の HTML ファイルでそれらをサポートします。
- **パック名の変更**: `ecosystem.json`の`pack_id`と`pack_identity`を変更してください。

---

## 関連ドキュメント

- [パック開発ガイド](../../pack-development.md)
- [多言語パック開発ガイド](../../multilang_pack_guide.md)
- [コアビューア機能](../../../core_runtime/core_pack/core_viewer_capability/)
