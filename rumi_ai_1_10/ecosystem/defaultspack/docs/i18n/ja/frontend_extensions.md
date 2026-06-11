<!-- docs-i18n-links:start -->
[EN](../../frontend_extensions.md) | [JP](./frontend_extensions.md) | [KR](../ko/frontend_extensions.md) | [CN](../zh-cn/frontend_extensions.md)
<!-- docs-i18n-links:end -->

# defaultspack フロントエンド拡張機能

`defaultspack` のスタンドアロン フロントエンドは「特定の UI を認識」せず、バックエンドから返されたレジストリを読み取り、シェル レイアウト、右バー、設定、およびチャット レンダラーを構成します。

## 最初に知っておくべきこと

- バックエンドコントラクトは`domain/frontend/registry.py`です
- スタンドアロン フロントエンドは `webapp/src/App.tsx`
- 右サイドバーは`webapp/src/components/RightSidebar.tsx`です
- 設定は`/api/ui/settings`です
- プレビュー フィードは `/api/ui/conversations/{id}/preview` です
- シェルレイアウトが`user_data/shared/frontend_shell.json`から置き換えられました

## 拡張ポイント

### ロード順序とアクティベーション

バックエンド拡張機能マニフェストは次の順序でロードされます。

1. `ecosystem/defaultspack/extensions/`
2.選択した兄弟パックの`extensions/`
3. `ecosystem/defaultspack/user_data/shared/extensions/`
4. `RUMI_DEFAULTSPACK_EXTENSION_ROOTS` で指定された追加のルート

フロントエンド拡張マニフェストは兄弟パックの `frontend_extensions/` です
`user_data/shared/frontend_extensions/`からロードされました。

`user_data/settings/setup_pack_selection.json`をお持ちの場合、兄弟パックは
`target_pack_ids` / `active_target_pack_id` / 従来の `target_pack_id` に含まれています
パックのみ有効です。 `defaultspack` とユーザー オーバーレイは常にロードされます。
選択ファイルのない開発環境では、すべての兄弟パックが通常どおりロードされます。

### 0. シェルレイアウトを置き換える

`user_data/shared/frontend_shell.json`内に`shell_layout`を配置することで、既存のReactを編集することなく、表示領域を並べ替えたり、無効にしたりすることができます。

```json
{
  "shell_layout": {
    "id": "compact",
    "regions": [
      { "id": "title_bar", "part_id": "app_chrome", "renderer": "title_bar", "slot": "top", "order": 10, "enabled": true },
      { "id": "history", "part_id": "conversation_history", "renderer": "history_board", "slot": "left", "order": 20, "enabled": false },
      { "id": "chat_messages", "part_id": "ai_chat", "renderer": "chat_messages", "slot": "main", "order": 40, "enabled": true },
      { "id": "composer", "part_id": "ai_chat", "renderer": "composer", "slot": "bottom", "order": 50, "enabled": true }
    ]
  }
}
```

`shell_renderers` は、レンダラー ID とフロントエンド コンポーネント名の間の契約を表します。組み込みレンダラーは `webapp/src/renderers/` に分割されており、`module` および `trust: "local"` を指定する同じ起源の `/static/renderers/`、`/static/assets/renderers/`、`/static/user_renderers/` でのみ遅延ロードできます。ロードが失敗した場合は、エラー境界で組み込みのフォールバックに戻ります。

```json
{
  "shell_renderers": [
    {
      "id": "composer",
      "component": "Composer",
      "regions": ["composer"],
      "fallback": "hidden",
      "module": "/static/renderers/custom-composer.js",
      "export": "default",
      "trust": "local"
    }
  ]
}
```

`/api/ui/catalog` は、壊れた `parts`、`component_bindings`、`shell_layout`、`shell_renderers` を `diagnostics` として返します。フロントエンドは診断を表示および記録できますが、マニフェスト全体を強制的に拒否することはありません。

### 1. 右側のバーに項目を追加します

`sidebar_items`を`user_data/shared/frontend_extensions/*.ui.json`に追加します。

```json
{
  "sidebar_items": [
    {
      "id": "weather-widget",
      "label": "Weather",
      "category": "widget",
      "description": "天気 widget の状態と設定",
      "panel": {
        "kind": "info",
        "title": "Weather",
        "notes": [
          "ここに widget の説明や導線を置ける"
        ],
        "fields": [
          {
            "id": "city",
            "label": "City",
            "type": "text",
            "default": "Tokyo"
          }
        ]
      }
    }
  ]
}
```

`category`は、`tool`、`widget`、`system`、`integration`のいずれかです。

## 2. 設定を追加する

同じマニフェストに `settings_sections` を追加します。

```json
{
  "settings_sections": [
    {
      "id": "weather",
      "label": "Weather",
      "description": "天気系 widget の共通設定",
      "fields": [
        {
          "id": "units",
          "label": "Units",
          "type": "select",
          "default": "metric",
          "options": [
            { "value": "metric", "label": "Metric" },
            { "value": "imperial", "label": "Imperial" }
          ]
        }
      ]
    }
  ]
}
```

保存先は`user_data/shared/frontend_settings.json`です。フロントエンドはスキーマを調べてフォームを自動的に生成します。

## 3. チャット描画を拡張する

レジストリは `chat_renderers` で、「どのブロック/ウィジェット タイプがどのレンダラーによって処理されるか」に関するメタデータを返します。

```json
{
  "chat_renderers": [
    {
      "id": "weather-card",
      "component": "WeatherCard",
      "block_types": ["weather"],
      "fallback": "json"
    }
  ]
}
```

このメタデータ自体はコントラクトであり、実際のレンダラー実装は組み込みレンダラー レジストリに追加されます。

現在の組み込みレンダラー:

- `text`、`markdown`
- `code`
- `image`
- `widget` フォールバック
- 不明なブロック フォールバック (`json` / `text` / `hidden`)

## 4. 右バーにツールスキーマを自動反映

`ToolRegistry`に登録されたツールは自動的に右側のサイドバー項目になります。各ツールの`schema.parameters`はパネルフィールドに変換されます。

つまり、ツールの数を増やすだけで、右側のバーの項目の数が増えます。

## 5. プレビューフィードを増やす

プレビュー フィードには、次のソースが集約されます。

- `tools_called`/`Inspector`
- `context_info.knowledge_results`
- `context_info.memory_results`
- メッセージ`widget`
- メッセージの`content`に`code` / `image`が含まれる

新しいプレビューを追加したい場合は、`_preview_from_log()` または `domain/frontend/registry.py` の `_preview_from_message()` を展開します。

## 設計ポリシー

- フロントエンドは「ツール」が何なのかを知りません
- バックエンドは「画面の完全な形式」を知りません
- 両者はレジストリ/スキーマ/プレビュー契約によってのみ接続されます
- 追加はマニフェストとレンダラ実装の 2 か所のみで行う必要があります。

## 変更時の確認

```bash
cd ecosystem/defaultspack/webapp
npm test
npm run lint
npm run build

cd ../../..
python -m pytest tests/test_defaultspack_ui_registry.py
```
