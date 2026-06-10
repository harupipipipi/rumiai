<!-- docs-i18n-links:start -->
[EN](./frontend_extensions.md) | [JP](./i18n/ja/frontend_extensions.md) | [KR](./i18n/ko/frontend_extensions.md) | [CN](./i18n/zh-cn/frontend_extensions.md)
<!-- docs-i18n-links:end -->

# defaultspack Frontend Extensions

The standalone frontend in `defaultspack` does not "know the specific UI" but rather reads the registry returned by the backend and configures the shell layout, right bar, settings, and chat renderer.

## Things to know first

- backend contract is `domain/frontend/registry.py`
- standalone frontend is `webapp/src/App.tsx`
- right sidebar is `webapp/src/components/RightSidebar.tsx`
- settings are `/api/ui/settings`
- preview feed is `/api/ui/conversations/{id}/preview`
- shell layout is replaced from `user_data/shared/frontend_shell.json`

## Extension points

### Load order and activation

The backend extension manifest is loaded in the following order.

1. `ecosystem/defaultspack/extensions/`
2. `extensions/` of the selected sibling pack
3. `ecosystem/defaultspack/user_data/shared/extensions/`
4. Additional roots specified in `RUMI_DEFAULTSPACK_EXTENSION_ROOTS`

frontend extension manifest is sibling pack's `frontend_extensions/`
Loaded from `user_data/shared/frontend_extensions/`.

If you have `user_data/settings/setup_pack_selection.json`, the sibling pack is
Included in `target_pack_ids` / `active_target_pack_id` / legacy `target_pack_id`
Only pack is valid. `defaultspack` and user overlay are always loaded.
In a development environment without a selection file, all sibling packs are loaded as usual.

### 0. Replace shell layout

By placing `shell_layout` in `user_data/shared/frontend_shell.json`, you can rearrange or disable displayed regions without editing existing React.

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

`shell_renderers` represents the contract between renderer ID and frontend component name. The builtin renderer is divided into `webapp/src/renderers/`, and can only be lazy loaded under `/static/renderers/`, `/static/assets/renderers/`, `/static/user_renderers/` of the same origin that specifies `module` and `trust: "local"`. If loading fails, return to builtin fallback with error boundary.

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

`/api/ui/catalog` returns broken `parts`, `component_bindings`, `shell_layout`, `shell_renderers` as `diagnostics`. The frontend can display and record diagnostics, but does not forcefully reject the entire manifest.

### 1. Add items to the right bar

Add `sidebar_items` to `user_data/shared/frontend_extensions/*.ui.json`.

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

`category` is one of `tool`, `widget`, `system`, `integration`.

## 2. Add settings

Add `settings_sections` to the same manifest.

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

The save destination is `user_data/shared/frontend_settings.json`. The frontend looks at the schema and automatically generates the form.

## 3. Extend Chat drawing

The registry is `chat_renderers` and returns metadata about ``which block/widget type is handled by which renderer.''

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

This metadata itself is a contract, and the actual renderer implementation is added to the builtin renderer registry.

Current builtin renderer:

- `text`, `markdown`
- `code`
- `image`
- `widget` fallback
- unknown block fallback (`json` / `text` / `hidden`)

## 4. Automatically reflect Tool schema to the right bar

Tools registered in `ToolRegistry` automatically become right sidebar items. `schema.parameters` for each tool is converted to a panel field.

In other words, simply increasing the number of tools will increase the number of items on the right bar.

## 5. Increase Preview feed

The preview feed aggregates the following sources.

- `tools_called` of `Inspector`
- `context_info.knowledge_results`
- `context_info.memory_results`
- message `widget`
- `code` / `image` included in `content` of message

If you want to add new previews, expand `_preview_from_log()` or `_preview_from_message()` of `domain/frontend/registry.py`.

## Design policy

- frontend doesn't know what "tool" is
- The backend does not know the "complete form of the screen"
- Both parties are connected only by registry/schema/preview contract
- Additions only need to be made in two places: manifest and renderer implementation

## Confirmation when changing

```bash
cd ecosystem/defaultspack/webapp
npm test
npm run lint
npm run build

cd ../../..
python -m pytest tests/test_defaultspack_ui_registry.py
```
