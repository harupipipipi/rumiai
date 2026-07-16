# Entity picker contract

`entity_picker` is the generic declarative selector for opaque catalog entities. Packs supply metadata, a registered data source, and optional registered actions; the shell owns search, grouping, keyboard behavior, optimistic state, pagination, and presentation. Packs must not ship feature-specific React for picker behavior.

## Declaration

```json
{
  "id": "agent_profile_picker",
  "kind": "entity_picker",
  "picker": {
    "api_version": "rumi.entity_picker.v1",
    "picker_id": "agent_profile",
    "label": "Agent profile",
    "description": "Choose one or more profiles",
    "trigger_command": "/agent-profile",
    "presentation": "popup",
    "selection_mode": "multi",
    "value_scope": "workspace",
    "data_source": "agent_profiles",
    "on_select_action_id": "profiles.select",
    "id_path": "profile.id",
    "label_path": "profile.name",
    "description_path": "profile.summary",
    "group_by_path": "team",
    "badges_path": "badges",
    "disabled_path": "disabled",
    "disabled_reason_path": "disabled_reason",
    "favorite_path": "favorite",
    "recent_path": "recent",
    "fixed_entries": [
      { "id": "inherit", "label": "Inherit" },
      { "id": "auto", "label": "Auto" },
      { "id": "none", "label": "None" }
    ],
    "create_item": {
      "label": "Create profile",
      "action_id": "profiles.create"
    }
  }
}
```

Supported presentations are `popup`, `palette`, `inline`, `settings`, and `status_surface`. Selection is `single` or `multi`. Value scope is `draft`, `conversation`, `run`, `settings`, `workspace`, or `global`. `draft` is ephemeral; every persistent scope requires `on_select_action_id`.

When `trigger_command` is present the projector adds a normal Composer command with a greedy `query` argument and the frontend action `open_entity_picker`. The same `EntityPickerHost` renders inline settings and status-surface controls.

## Data sources and actions

`data_source` must identify a registered catalog data source. A local source may expose bounded items in `snapshot.items`, `snapshot.results`, `data.items`, or `data.results`. A remote source declares `remote: true` and a registered `load_action_id`; requests contain only `picker_id`, `query`, optional `cursor`, and `data_source_id`.

Selection actions receive typed values only:

```json
{
  "picker_id": "agent_profile",
  "selected_ids": ["reviewer"],
  "data_source_id": "agent_profiles",
  "source_revision": "r8",
  "value_scope": "workspace"
}
```

The browser never executes arbitrary JavaScript, fetches declaration URLs, or evaluates object paths. IDs are bounded opaque tokens. Paths are bounded dot-separated field names and reject prototype-related segments. Items are capped at 500, deduplicated by ID, and normalized to label, description, icon ID, group, badges, disabled reason, favorite, and recent state. Disabled items cannot be selected.

## Interaction and failure behavior

- Search is local for snapshots and debounced for remote sources. Cursor pagination merges by opaque ID.
- Create is ordered first, followed by favorites, recent items, groups, labels, and IDs.
- Arrow keys move the active option, Enter selects, Escape closes, and normal Tab navigation is retained. Focus moves to search on open and returns to the prior control on close.
- Single selection commits immediately. Multi selection commits with Apply.
- Selection is optimistic. Backend rejection restores the previous selection and exposes an alert without discarding the picker.
- Missing sources/actions, unsafe paths, incompatible versions, or invalid IDs fail closed into an attributable unsupported fallback. Disabling a pack removes its picker on the next catalog refresh.
