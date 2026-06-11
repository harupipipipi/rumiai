<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# Rumi ブラウザ コンパニオン

`Rumi Browser Companion` は、Rumi がローカル ブリッジ経由でユーザーの実際のブラウザ セッションを駆動できるようにする Manifest V3 Chromium 拡張機能です。これは、既存の `browser_use` および `computer_use` ツールを補完するように設計されています。

- `computer_use` / `browser_computer`: 可視ウィンドウ、コンピュータ使用のスタイル コントロール
- `browser_companion`: ユーザーのサインインしているブラウザー プロファイル内の DOM 対応ブラウザー コントロール

これにより、モデルが DOM 状態を検査し、接続されているブラウザを選択し、ユーザーのライブ Cookie とセッションを操作できる「コンピュータの使用 + ブラウザの使用」パスが Rumi に与えられます。

## ファイル

- `manifest.json`: 拡張マニフェスト
- `background.js`: ブリッジポーリング、ブラウザメタデータ、タブ操作、キャプチャオーケストレーション
- `content_script.js`: DOM スナップショットと要素レベルのアクション
- `options.html`、`options.css`、`options.js`: ローカルブリッジ設定 UI

## インストール

1. Chrome、Edge、Brave、Vivaldi などの Chromium ベースのブラウザを開きます。
2. ブラウザの拡張機能ページを開き、開発者モードを有効にします。
3. [解凍してロード] を選択し、次のフォルダーを選択します。

   `<repo>/rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/rumi_browser_companion`

4. Rumi で、`browser_companion` を `action: "bridge.pairing"` とともに呼び出して、ペアリング トークンと候補サーバー URL を取得します。
5. 拡張機能のオプション ページを開いて、以下を貼り付けます。

   - `Server URL` `http://127.0.0.1:8766`など
   - `Pairing Token`

6. `Poll Bridge Now` をクリックして、拡張機能が接続できることを確認します。

## ブリッジ API

拡張機能は次のローカル エンドポイントと通信します。

- `POST {serverUrl}/api/tools/browser-companion/bridge/poll`
- `POST {serverUrl}/api/tools/browser-companion/bridge/result`

`poll` リクエスト本文:

```json
{
  "pairing_token": "example-token",
  "client": {
    "client_id": "uuid",
    "label": "My Edge Companion",
    "browser_name": "Microsoft Edge",
    "browser_version": "136.0.0.0",
    "extension_version": "0.1.0",
    "platform": "Win32",
    "user_agent": "...",
    "active_tab_id": 123,
    "tabs": [
      {
        "id": 123,
        "windowId": 1,
        "active": true,
        "title": "Example",
        "url": "https://example.com",
        "status": "complete"
      }
    ]
  }
}
```

`poll` 応答本文:

```json
{
  "status": "ok",
  "data": {
    "accepted": true,
    "client_id": "uuid",
    "command": {
      "command_id": "cmd_123",
      "action": "page.snapshot",
      "payload": {
        "tab_id": 123,
        "include_capture": true,
        "limit": 200
      }
    }
  }
}
```

`result` リクエスト本文:

```json
{
  "pairing_token": "example-token",
  "client_id": "uuid",
  "results": [
    {
      "command_id": "cmd_123",
      "ok": true,
      "result": {
        "snapshot": {
          "url": "https://example.com",
          "title": "Example",
          "nodes": []
        }
      }
    }
  ]
}
```

## サポートされているアクション

- `browser.tabs`
- `browser.select_tab`
- `page.navigate`
- `page.snapshot`
- `page.capture`
- `page.click`
- `page.type`
- `page.press`
- `page.scroll`
- `page.extract`

## 安全上の注意事項

- この拡張機能は、ユーザーの実際のブラウザ プロファイル内のページを検査して操作できます。
- あなたが制御するローカル Rumi サーバーとのみペアリングしてください。
- ペアリングトークンを共有しないでください。
- キャプチャとタブの選択により、ブラウザのタブが前面に表示される場合があります。
- DOM アクションはベストエフォート型であり、すべてのページで機能するとは限りません。

## 注意事項

- 拡張機能はユーザーの実際のブラウザ プロファイルを使用するため、認証されたページはユーザーの既存の Cookie およびセッションで動作します。
- DOM スナップショットと要素アクションは、コンテンツ スクリプトがすでに読み込まれているタブをターゲットにすることができます。
- 表示タブのキャプチャはブラウザのアクティブな表示タブに依存するため、キャプチャ リクエストによりターゲット タブがアクティブになる場合があります。
