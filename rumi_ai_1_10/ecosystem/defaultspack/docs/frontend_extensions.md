# defaultspack Frontend Extensions

`defaultspack` の standalone frontend は「具体 UI を本体が知る」のではなく、backend が返す registry を読んで shell layout・右バー・設定・chat renderer を構成する。

## まず知っておくこと

- backend contract は `domain/frontend/registry.py`
- standalone frontend は `webapp/src/App.tsx`
- right sidebar は `webapp/src/components/RightSidebar.tsx`
- settings は `/api/ui/settings`
- preview feed は `/api/ui/conversations/{id}/preview`
- shell layout は `user_data/shared/frontend_shell.json` から差し替えられる

## 拡張ポイント

### 0. Shell layout を差し替える

`user_data/shared/frontend_shell.json` に `shell_layout` を置くと、既存 React を編集せずに表示 region を並べ替えたり無効化できる。

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

`shell_renderers` は renderer ID と frontend component 名の契約を表す。現段階では trusted builtin renderer だけを実行し、未知の renderer は fallback metadata として扱う。

```json
{
  "shell_renderers": [
    { "id": "composer", "component": "Composer", "regions": ["composer"], "fallback": "hidden" }
  ]
}
```

### 1. 右バーに項目を追加する

`user_data/shared/frontend_extensions/*.ui.json` に `sidebar_items` を追加する。

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

`category` は `tool`, `widget`, `system`, `integration` のいずれか。

## 2. 設定を追加する

同じ manifest に `settings_sections` を追加する。

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

保存先は `user_data/shared/frontend_settings.json`。frontend は schema を見て form を自動生成する。

## 3. Chat 描画を拡張する

registry は `chat_renderers` で「どの block/widget type をどの renderer が担当するか」の metadata を返す。

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

この metadata 自体は契約で、実際の renderer 実装は builtin renderer registry に追加する。

今の builtin renderer:

- `text`, `markdown`
- `code`
- `image`
- `widget` fallback
- unknown block fallback (`json` / `text` / `hidden`)

## 4. Tool schema を右バーへ自動反映する

`ToolRegistry` に登録された tool は自動で right sidebar item になる。tool ごとの `schema.parameters` は panel field に変換される。

つまり tool を増やすだけでも右バーに項目が増える。

## 5. Preview feed を増やす

preview feed は次のソースを集約している。

- `Inspector` の `tools_called`
- `context_info.knowledge_results`
- `context_info.memory_results`
- message の `widget`
- message の `content` に含まれる `code` / `image`

新しい preview を増やしたいときは `domain/frontend/registry.py` の `_preview_from_log()` または `_preview_from_message()` を拡張する。

## 設計方針

- frontend は「tool が何か」を知らない
- backend は「画面の完成形」を知らない
- 両者は registry/schema/preview contract だけで結ばれる
- 追加は manifest と renderer 実装の 2 箇所で済ませる

## 変更時の確認

```bash
cd ecosystem/defaultspack/webapp
npm test
npm run lint
npm run build

cd ../../..
python -m pytest tests/test_defaultspack_ui_registry.py
```
