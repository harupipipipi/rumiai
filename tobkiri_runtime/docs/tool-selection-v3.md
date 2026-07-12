# Tool Selection UX v3

This document fixes the product and technical contract for the Tool UX v3 vertical slice.

## Goals

- Users can use Rumi without opening a raw Tool list.
- Composer shows only the current-turn choice: auto, review, manual, or none.
- The right panel is a Tool Hub for discovery, recommendations, pins, recent use, and connections.
- Settings owns durable defaults, permissions, connections, and advanced selector strategy.
- Tool selection and Tool execution approval are separate layers.
- Auto selection hydrates full provider schemas only after final selection, except explicit debug strategies.
- Selector failure falls back without stopping the chat.
- Local-first operation remains safe when embeddings or cloud keys are unavailable.

## User Concepts

User-facing copy should prefer `機能` over `Tool`.

| Mode | Meaning |
| --- | --- |
| `auto` | Rumi selects the needed features. |
| `review` | Rumi previews candidates and waits for user confirmation. |
| `manual` | Only user-selected features are candidates. |
| `none` | No external features are used for this message. |

Advanced implementation terms such as `hybrid`, `semantic`, `all_schemas`, and selector model choices belong in Settings only.

## State Layers

Tool state is split into five layers:

- Connection: `connected`, `setup_required`, `unavailable`, `error`.
- Execution permission: `auto`, `confirm`, `block`.
- Display state: `pinned`, `hidden`, `recent`.
- Conversation state: include, exclude, and mode override persisted in conversation metadata.
- Turn state: include, exclude, and mode override cleared after send.

`hidden` only hides a tool from lists. It is not a block. `block` removes the tool from selector candidates and runtime execution.

## Settings v3

`frontend_settings.json` stores:

```json
{
  "tools": {
    "settings_version": 3,
    "default_mode": "auto",
    "selection_strategy": "hybrid",
    "semantic_backend": "auto",
    "semantic_candidate_limit": 32,
    "final_tool_limit": 8,
    "selector_model": "",
    "selector_trace": "summary",
    "show_selection_summary": true,
    "show_selection_reasons": false,
    "action_permissions": {
      "read": "auto",
      "search": "auto",
      "create": "confirm",
      "update": "confirm",
      "send": "confirm",
      "execute": "confirm",
      "computer": "confirm",
      "delete": "confirm"
    },
    "service_permission_overrides": {},
    "tool_permission_overrides": {},
    "pinned_service_ids": [],
    "hidden_tool_ids": []
  }
}
```

Migration rules:

- v2 and legacy `tool_assist_mode=all|auto` become `default_mode=auto`, `selection_strategy=hybrid`.
- `tool_assist_mode=vector` becomes `selection_strategy=lexical`.
- `tool_assist_mode=off|manual` becomes `default_mode=manual`.
- `disabled_tool_ids` become `tool_permission_overrides[id] = "block"`.
- `hidden_tool_ids` stay hidden display state.
- Legacy active selected tools must not become conversation locks automatically.

## Selection Strategies

| Strategy | Behavior |
| --- | --- |
| `hybrid` | Semantic or lexical candidate search, then utility selector AI chooses final tools. |
| `semantic` | Embedding-backed semantic search, falling back to lexical search. |
| `catalog_ai` | Utility selector AI chooses from the compact eligible catalog. |
| `all_with_hints` | All eligible schemas plus recommendation hints, with provider-limit fallback. |
| `all_schemas` | All eligible full schemas for debug use. |
| `lexical` | Lightweight lexical search. |

Selector AI receives only compact catalog records, never full schemas, secrets, approval tokens, or attached file bodies. It must not receive tools.

## Backend Pipeline

```text
request normalization
  -> static eligibility
  -> service catalog and permission resolution
  -> strategy selection
  -> selector ID validation
  -> final schema hydration
  -> model routing and dynamic eligibility
  -> provider planning
  -> main AI
  -> execution-time permission and approval enforcement
```

`confirm` tools may be selected. `block` tools may not be selected or executed. Existing runtime approval remains the final authority for writes, sends, shell/file mutations, browser/computer control, git actions, and secrets.

## API Contract

New frontend sends structured `params.tool_selection`:

```json
{
  "mode": "auto",
  "strategy": null,
  "scope": "turn",
  "include": [{ "kind": "service", "id": "github" }],
  "exclude": [{ "kind": "tool", "id": "github.create_issue" }],
  "must_use": false,
  "preview_id": null
}
```

Legacy support remains:

- omitted `tools`: auto selection.
- `tools: []`: no tools.
- `tools: [id]`: manual include.
- string includes become `{ "kind": "tool", "id": "..." }`.

Additional APIs:

- `GET /api/tools/catalog`
- `POST /api/tools/selection/preview`
- `GET /api/tools/selection/traces/{trace_id}`
- `GET /api/chat/conversations/{id}/tool-preferences`
- `PUT /api/chat/conversations/{id}/tool-preferences`
- `POST /api/tools/embedding-index/rebuild`

## Frontend Contract

Composer:

- Adds `ToolModeControl` using the existing 36px composer control surface.
- Labels: `機能 自動`, `機能 確認`, `機能 手動`, `機能 なし`.
- Turn chips clear after successful send.
- Conversation chips persist through the conversation preferences API.
- Review mode waits for preview approval before starting the main stream.

Tool Hub:

- Replaces the ordinary raw per-tool toggle list.
- Shows recommendations, pinned services, recently used services, and connections.
- Groups tools under services such as GitHub, Web, Files, Gmail, Browser, and Computer.
- Raw Tool IDs appear only in Technical details.

Settings:

- Section label is `機能と接続`.
- Tabs: Basic, Permissions, Connections, Advanced.
- Permissions use `auto / confirm / block`.
- Individual tool controls move to Advanced.
- `Hide` copy becomes `一覧から隠す`.

## Acceptance

- Normal auto mode sends only final selected full schemas to the main model.
- `auto`, `review`, `manual`, and `none` all work.
- `turn` and `conversation` scopes work and are visibly distinct.
- Embedding absence is a normal lexical fallback.
- Advanced Settings can choose all selection strategies.
- Selection reasons and fallback details are inspectable without showing chain of thought.
- Dangerous actions cannot bypass existing approval.
- Desktop, mobile, keyboard, and screen reader flows are covered by tests.
