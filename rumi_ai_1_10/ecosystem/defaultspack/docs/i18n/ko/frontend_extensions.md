<!-- docs-i18n-links:start -->
[EN](../../frontend_extensions.md) | [JP](../ja/frontend_extensions.md) | [KR](./frontend_extensions.md) | [CN](../zh-cn/frontend_extensions.md)
<!-- docs-i18n-links:end -->

# defaultspack 프런트엔드 확장

`defaultspack`의 독립형 프런트엔드는 "특정 UI를 알지" 못하고 백엔드에서 반환된 레지스트리를 읽고 셸 레이아웃, 오른쪽 표시줄, 설정 및 채팅 렌더러를 구성합니다.

## 먼저 알아야 할 사항

- 백엔드 계약은 `domain/frontend/registry.py`입니다.
- 독립형 프런트엔드는 `webapp/src/App.tsx`입니다.
- 오른쪽 사이드바는 `webapp/src/components/RightSidebar.tsx`입니다.
- 설정은 `/api/ui/settings`입니다.
- 미리보기 피드는 `/api/ui/conversations/{id}/preview`입니다.
- 쉘 레이아웃이 `user_data/shared/frontend_shell.json`에서 대체되었습니다.

## 확장 포인트

### 로드 순서 및 활성화

백엔드 확장 매니페스트는 다음 순서로 로드됩니다.

1. `ecosystem/defaultspack/extensions/`
2. 선택한 형제 팩의 `extensions/`
3. `ecosystem/defaultspack/user_data/shared/extensions/`
4. `RUMI_DEFAULTSPACK_EXTENSION_ROOTS`에 명시된 추가근

프런트엔드 확장 매니페스트는 형제 팩의 `frontend_extensions/`입니다.
`user_data/shared/frontend_extensions/`에서 로드됩니다.

`user_data/settings/setup_pack_selection.json`가 있는 경우 형제 팩은 다음과 같습니다.
`target_pack_ids` / `active_target_pack_id` / 레거시 `target_pack_id`에 포함됨
팩만 유효합니다. `defaultspack` 및 사용자 오버레이가 항상 로드됩니다.
선택 파일이 없는 개발 환경에서는 모든 형제 팩이 평소대로 로드됩니다.

### 0. 쉘 레이아웃 교체

`user_data/shared/frontend_shell.json`에 `shell_layout`을 배치하면 기존 React를 편집하지 않고도 표시된 영역을 재배열하거나 비활성화할 수 있습니다.

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

`shell_renderers`은 렌더러 ID와 프런트엔드 구성 요소 이름 간의 계약을 나타냅니다. 내장 렌더러는 `webapp/src/renderers/`로 나누어져 있으며, `module` 및 `trust: "local"`을 지정하는 동일한 출처의 `/static/renderers/`, `/static/assets/renderers/`, `/static/user_renderers/`에서만 지연 로드가 가능합니다. 로드에 실패하면 오류 경계가 있는 내장 폴백으로 돌아갑니다.

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

`/api/ui/catalog`는 깨진 `parts`, `component_bindings`, `shell_layout`, `shell_renderers`를 `diagnostics`로 반환합니다. 프런트엔드는 진단을 표시하고 기록할 수 있지만 전체 매니페스트를 강제로 거부하지는 않습니다.

### 1. 오른쪽 바에 항목을 추가합니다.

`user_data/shared/frontend_extensions/*.ui.json`에 `sidebar_items`를 추가합니다.

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

`category`는 `tool`, `widget`, `system`, `integration` 중 하나입니다.

## 2. 설정 추가

동일한 매니페스트에 `settings_sections`를 추가합니다.

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

저장 대상은 `user_data/shared/frontend_settings.json`입니다. 프런트엔드는 스키마를 보고 자동으로 양식을 생성합니다.

## 3. 채팅 그리기 확장

레지스트리는 `chat_renderers`이며 "어떤 블록/위젯 유형이 어떤 렌더러에 의해 처리되는지"에 대한 메타데이터를 반환합니다.

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

이 메타데이터 자체는 계약이며 실제 렌더러 구현은 내장 렌더러 레지스트리에 추가됩니다.

현재 내장 렌더러:

- `text`, `markdown`
- `code`
- `image`
- `widget` 대체
- 알 수 없는 블록 대체(`json` / `text` / `hidden`)

## 4. 도구 스키마를 오른쪽 막대에 자동으로 반영

`ToolRegistry`에 등록된 도구는 자동으로 오른쪽 사이드바 항목이 됩니다. 각 도구의 `schema.parameters`이 패널 필드로 변환됩니다.

즉, 단순히 도구 수를 늘리면 오른쪽 막대에 표시되는 항목 수가 늘어납니다.

## 5. 미리보기 피드 늘리기

미리보기 피드는 다음 소스를 집계합니다.

- `Inspector`의 `tools_called`
- `context_info.knowledge_results`
- `context_info.memory_results`
- 메시지 `widget`
- 메시지의 `content`에 `code` / `image` 포함

새로운 미리보기를 추가하려면 `_preview_from_log()` 또는 `domain/frontend/registry.py`의 `_preview_from_message()`을 확장하세요.

## 디자인 정책

- 프론트엔드는 "도구"가 무엇인지 모릅니다.
- 백엔드는 "화면의 완전한 형태"를 알지 못합니다.
- 양측은 레지스트리/스키마/미리보기 계약으로만 연결됩니다.
- 매니페스트와 렌더러 구현 두 곳에서만 추가하면 됩니다.

## 변경 시 확인

```bash
cd ecosystem/defaultspack/webapp
npm test
npm run lint
npm run build

cd ../../..
python -m pytest tests/test_defaultspack_ui_registry.py
```
