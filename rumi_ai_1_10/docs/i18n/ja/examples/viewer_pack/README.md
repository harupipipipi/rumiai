<!-- docs-i18n-links:start -->
[EN](../../../../examples/viewer_pack/README.md) | [JP](./README.md) | [KR](../../../ko/examples/viewer_pack/README.md) | [CN](../../../zh-cn/examples/viewer_pack/README.md)
<!-- docs-i18n-links:end -->

# ビューア サンプル パック

Rumi Viewer でフロントエンドを表示するために `viewer:display` 機能を使用するパックの最小限の例。

## 概要

このパックでは次の内容が表示されます。

- `viewer.display` 機能の宣言方法 (`manifest.json`、`requires`、`vocab_aliases`)
- `grant_config`による設定の付与
- `web_mount`によるフロントエンド配信
- `calling_convention: "block"`の関数スタブ

## ディレクトリ構造

```
viewer_pack/
├── ecosystem.json                    # Pack 定義（web_mount, functions）
├── functions/
│   └── request_display/
│       ├── manifest.json             # viewer.display capability 宣言
│       └── main.py                   # Function スタブ（block）
├── web/
│   ├── index.html                    # Pack フロントエンド
│   └── style.css                     # スタイル
└── README.md                         # このファイル
```

## 各ファイルの役割

### エコシステム.json

パックのマニフェスト。 `pack_id`、`metadata`、`web_mount`、`functions`を定義します。
`web_mount` フィールドは、Rumi Viewer 内の `web/` ディレクトリの内容を提供します。

### 関数/request_display/manifest.json

`viewer.display` 機能の詳細な宣言。次のフィールドが重要です。

- **`requires`**: `["viewer.display"]` — この関数に必要な機能
- **`vocab_aliases`**: `["viewer.display"]` — FunctionRegistry のエイリアス解決に使用されます
- **`grant_config`**: 付与設定(`allowed_packs`、`max_token_lifetime`)
- **`calling_convention`**: `"block"` — カーネルの DI ハンドラ経由で実行

### 関数/request_display/main.py

`calling_convention: "block"`の書きかけです。実行時のカーネル DI ハンドラー
(`handle_display`) なので、このファイルが直接実行されることはありません。
パック構造の整合性のために存在します。

### web/index.html、web/style.css

これは Pack のフロントエンドです。 Rumi Viewer のサンドボックス WebView 内にロードされます。
CDN は使用せず、プレーンな HTML/CSS で記述します。

## ビューア:表示機能の仕組み

1. パックリクエスト `viewer.display` 機能
2. `capability_executor` は `FunctionRegistry.resolve_by_alias("viewer.display")` によって解決されました
3. `grant_config` が設定されている場合、`capability_grant_manager` は許可をチェックします。
4. `calling_convention: "block"` → カーネルDIハンドラ(`handle_display`)実行
5.トークンと`web_mount_url`が返却されます
6. Rumi Viewer は `web_mount_url` をサンドボックス WebView にロードします

## 助成金の取得

このパックには、`viewer.display` 機能を使用する許可が必要です。
補助金は`capability_grant_manager`によって管理されます。

- **`allowed_packs`**: 空の配列 `[]`の場合、すべてのパックからのリクエストを許可します
- **`max_token_lifetime`**: トークンの最大有効期限 (秒)

補助金の仕組みの詳細については、[パック開発ガイド セクション 6](../../pack-development.md) を参照してください。

## 関連ドキュメント

- [パック開発ガイド](../../pack-development.md) — パックの構造、ライフサイクル、および機能の詳細
- [多言語パック開発ガイド](../../multilang_pack_guide.md) — Python 以外の言語でパックを開発する方法
