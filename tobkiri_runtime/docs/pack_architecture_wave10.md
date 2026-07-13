# Pack Architecture Wave 10

Wave 10 reduces `defaultspack` to finite compatibility facades. A retained
legacy path may expose an old HTTP/function identifier, export an old snapshot,
or diagnose a missing migration; it may not own primary state, dispatch work,
or render the primary feature UI.

## Kanban cutover boundary

`rumi_kanban_state_store_pack` is the new authoritative owner. Its resource
contract now has board, card, and column lookup operations so a legacy route
shim never opens a second state store. The defaultspack Kanban block remains
temporarily only because it is the source of the current SQLite snapshot and
legacy HTTP route IDs.

The legacy `/api/kanban/*` block now dispatches through
`domain.kanban.contract_facade` rather than constructing `KanbanService`.
Mutations are translated to exact revision-bound owner actions and require a
locally validated approval token unless the call originates from the internal
tool-server approval context. A new explicit
`POST /api/kanban/boards/{board_id}/migrate` alias performs the caller-selected
snapshot export and one-shot owner import. The remaining agent/sync aliases
return `KANBAN_LEGACY_ACTION_DEPRECATED` until their contract-native adapters
are selected; they do not resume the old service.

The legacy `tool_task_board` and `tool_task_board_agent_session` handlers now
return stable `*_LEGACY_TOOL_DEPRECATED` recovery diagnostics. Their former
SQLite writers, JSON import, and direct agent/session coupling were removed.
Those public IDs remain only until a selected task-board adapter exposes their
contract-native replacement; they must not silently recreate state in the
defaultspack namespace.

The defaultspack React workspace no longer imports Kanban components, resources,
or `/api/kanban` client methods. A legacy Kanban tab is now a finite navigation
shim to `/kanban`; the selected `rumi_kanban_surface_pack` owns the removable
isolated UI projection. The old component tree and its direct API test were
removed rather than retained as a hidden fallback.

`domain/kanban/service.py` and `domain/kanban/store.py` have been removed.
The only legacy SQLite access is `legacy_snapshot_reader.py`, which opens the
selected database in SQLite `mode=ro`, performs no schema migration, and reads
only the board, column, card, and bounded event rows needed for a caller-
selected one-shot export.

The shim cutover must occur in this order:

1. Export a caller-selected old board through a migration-only entrypoint.
2. Redeem one exact `kanban.state.manage` receipt to invoke
   `migration.import_snapshot`.
3. Route all old reads and permitted mutations through
   `rumi.resource.kanban.v1` and `rumi.action.kanban.v1`.
4. Keep an old route only as a finite alias; it must return a supported
   migration diagnostic when the selected board has not been imported.
5. Enable `rumi_kanban_surface_pack` in the default profile only after the
   old primary React workspace view and direct resource client are removed.

This sequence intentionally has no live fallback to the SQLite owner and no
dual write. A failed or changed source snapshot is fail-closed and provides a
recovery path: restore the selected old owner snapshot, or retry the identical
source through the one-shot import before routing any writes.

## Remaining defaultspack inventory

| Legacy surface | Allowed remaining role | Forbidden role after cutover |
|---|---|---|
| `/api/kanban/*` | finite route aliases and migration diagnostics | direct `KanbanService` construction or SQLite access outside migration export |
| `legacy_snapshot_reader.py` | caller-selected read-only snapshot export | schema migration, DB creation, state read/write fallback |
| React Kanban workspace | temporary deprecated route shim | primary UI, direct API client, direct implementation URL |
| `tool_task_board*` | explicit deprecated tool diagnostics | SQLite/JSON state ownership or agent/session dispatch |
| `rumi_kanban_surface_pack` | selected isolated read-only content | state/action ownership or receipt handling |

## Release boundary

The compatibility shim must emit a stable machine-readable code for each
unsupported old action, missing selected provider, migration-required board,
and stale revision. It must never silently recreate an old board in the new
store. Rollback selects one prior owner before reopening the legacy route; it
does not replay writes into both stores.

Focused runtime, migration, and cross-platform validation are specified in
`docs/qa/pack_architecture_wave10_qa.md`. This document is a plan and static
ownership record, not execution evidence.

テスト、lint、build、起動確認、実環境確認は実装担当のCodexでは実行していません。
マージ前に独立した実環境QAが必要です。
