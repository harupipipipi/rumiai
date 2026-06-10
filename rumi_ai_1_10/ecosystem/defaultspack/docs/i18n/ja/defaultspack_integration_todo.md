<!-- docs-i18n-links:start -->
[EN](../../defaultspack_integration_todo.md) | [JP](./defaultspack_integration_todo.md) | [KR](../ko/defaultspack_integration_todo.md) | [CN](../zh-cn/defaultspack_integration_todo.md)
<!-- docs-i18n-links:end -->

#defaultspack 統合 TODO

## 目標

defaultspack は、Rumi が提供するパックデスクトップアプリです。そのフロントエンドは、バックエンド コンポーネントの固定された所有者ではなく、交換可能なシェルのままでなければなりません。

## 原則

- 部品はデータとして宣言されます。フロントエンドはパートコントラクトを受け取り、理解したものをレンダリングします。
- コンポーネントは、新しいコンポーネントごとに React を編集するのではなく、マニフェスト/構成を提供することによってパーツの使用方法を決定します。
- バックエンド機能/コンポーネント名は、`/api/ui/*` 契約の後に残ります。
- ユーザー オーバーレイは、`user_data/shared/frontend_extensions/*.ui.json` を通じてデフォルト パーツを置き換えたり拡張したりできます。
- UI は後で破棄できます。コントラクト、マニフェスト、ルート、アイコン アセット パスは書き換え後も存続する必要があります。

## 現在のスライス

- [x] Rumi ファビコンをdefaultspack が所有するアセットに移動します。
- [x] React でアイコンをハードコーディングするのではなく、UI サーフェス設定を通じてアイコンを公開します。
- [x]defaultspack `desktop_app` メタデータを `ecosystem.json` に追加します。
- [x]defaultspack HTTP サーフェスを開く小さなデスクトップ ランチャーを追加します。
- [x] `/api/ui/catalog`、`/api/ui/settings`、`/api/ui/conversations/{id}/preview`を登録します。
- [x] スタンドアロン モード用のフォールバック HTTP ルートを追加します。
- [x] パーツとコンポーネント バインディング用の UI サーフェス設定スロットを追加します。
- [x] 型指定された API コントラクトを通じてフロントエンド アクセスを維持します。
- [x] シェル レイアウト/シェル レンダラー コントラクトを UI カタログに追加します。
- [x] React を編集せずに `user_data/shared/frontend_shell.json` でシェル レイアウトをオーバーライドします。
- [x] アプリのクロム、履歴、チャット、プレビュー、サイドバー、設定のスキーマを含むパーツを追加します。
- [x] シェル レイアウト コントラクトを通じて、表示されている React 領域をゲートします。
- [x] `webapp/src/renderers/` で、表示されている各 React 領域を独自の小さなレンダラー モジュールに分割します。
- [x] エラー境界とフォールバック レンダラーを使用して、信頼できるローカル バンドルに遅延カスタム レンダラーの読み込みを追加します。
- [x] 不正な形式の `parts`、`component_bindings`、`shell_layout`、および `shell_renderers` の検証診断を追加します。
- [x] プレビュー契約にツールのタイムライン、計画ステップ、承認、添付ファイル、およびオーディオ ペイロードの明示的なスキーマを追加します。
- [x] DI、権限設定、トークン発行、およびカーネル デスクトップ ハンドラーを介して許可フローを `desktop_app.execute` に接続します。
- [x] `RUMI_DEFAULTSPACK_SURFACE=webview` 経由でネイティブ Webview ラッパー オプションを追加します。

## 製品フォローアップノート

- 製品 UI の方向が設定された後、一時的な組み込みレンダラー ビジュアルを置き換えます。
- ネイティブ WebView がデフォルトになる場合のみ、`pywebview` をパッケージ化します。現在のデフォルトはブラウザのフォールバックのままです。
- ビューア UI がデスクトップ アプリの起動元を選択したら、エンドツーエンドのビューア クリック パスを追加します。
