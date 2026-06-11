<!-- docs-i18n-links:start -->
[EN](../../frontend_extensions.md) | [JP](../ja/frontend_extensions.md) | [KR](../ko/frontend_extensions.md) | [CN](./frontend_extensions.md)
<!-- docs-i18n-links:end -->

# defaultspack 前端扩展

`defaultspack` 中的独立前端并不“知道特定的 UI”，而是读取后端返回的注册表并配置 shell 布局、右栏、设置和聊天渲染器。

## 首先要知道的事情

- 后端合约为`domain/frontend/registry.py`
- 独立前端是`webapp/src/App.tsx`
- 右侧边栏为`webapp/src/components/RightSidebar.tsx`
- 设置为`/api/ui/settings`
- 预览提要是`/api/ui/conversations/{id}/preview`
- 外壳布局从`user_data/shared/frontend_shell.json`替换

## 扩展点

### 加载订单并激活

后端扩展清单按以下顺序加载。

1.`ecosystem/defaultspack/extensions/`
2.所选兄弟包的`extensions/`
3.`ecosystem/defaultspack/user_data/shared/extensions/`
4. `RUMI_DEFAULTSPACK_EXTENSION_ROOTS`中指定的附加根

前端扩展清单是同级包的`frontend_extensions/`
从`user_data/shared/frontend_extensions/`加载。

如果您有`user_data/settings/setup_pack_selection.json`，则兄弟包是
包含在`target_pack_ids`/`active_target_pack_id`/旧版`target_pack_id`中
仅包有效。 `defaultspack` 和用户叠加层始终加载。
在没有选择文件的开发环境中，所有同级包都会照常加载。

### 0.替换外壳布局

通过将`shell_layout`放置在`user_data/shared/frontend_shell.json`中，您可以重新排列或禁用显示区域，而无需编辑现有的React。

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

`shell_renderers` 表示渲染器 ID 和前端组件名称之间的约定。内置渲染器分为`webapp/src/renderers/`，并且只能在指定`module`和`trust: "local"`的同源`/static/renderers/`、`/static/assets/renderers/`、`/static/user_renderers/`下延迟加载。如果加载失败，则返回到带有错误边界的内置回退。

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

`/api/ui/catalog` 将损坏的`parts`、`component_bindings`、`shell_layout`、`shell_renderers`返回为`diagnostics`。前端可以显示和记录诊断信息，但不会强制拒绝整个清单。

### 1. 将项目添加到右侧栏

将`sidebar_items` 添加至`user_data/shared/frontend_extensions/*.ui.json`。

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

`category`是`tool`、`widget`、`system`、`integration`之一。

## 2.添加设置

将`settings_sections` 添加到同一清单中。

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

保存目的地是`user_data/shared/frontend_settings.json`。前端查看架构并自动生成表单。

## 3. 扩展聊天绘图

注册表为`chat_renderers`，并返回有关“哪个块/小部件类型由哪个渲染器处理”的元数据。

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

该元数据本身是一个契约，实际的渲染器实现被添加到内置渲染器注册表中。

当前内置渲染器：

- `text`，`markdown`
- `code`
- `image`
- `widget`后备
- 未知的块回退（`json` / `text` / `hidden`）

## 4. 自动将工具架构反映到右侧栏

在`ToolRegistry`中注册的工具自动成为右侧边栏项目。每个工具的`schema.parameters` 被转换为面板字段。

换句话说，简单地增加工具的数量就会增加右侧栏上的项目数量。

## 5.增加预览提要

预览源聚合了以下来源。

- `tools_called` of `Inspector`
- `context_info.knowledge_results`
- `context_info.memory_results`
- 消息`widget`
- `code` / `image` 包含在消息的`content` 中

如果要添加新预览，请展开`_preview_from_log()` 或`_preview_from_message()` 或`domain/frontend/registry.py`。

## 设计政策

- 前端不知道什么是“工具”
- 后端不知道“屏幕的完整形式”
- 双方仅通过注册表/架构/预览合约连接
- 只需要在两个地方进行添加：清单和渲染器实现

## 更改时确认

```bash
cd ecosystem/defaultspack/webapp
npm test
npm run lint
npm run build

cd ../../..
python -m pytest tests/test_defaultspack_ui_registry.py
```
