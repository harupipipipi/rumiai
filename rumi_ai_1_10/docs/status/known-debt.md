# Known Debt

Last updated: 2026-06-22

## P0

- keep pack function execution gates consistent across `function_id` routes, `function.call`, and permission-based execution paths
- continue reducing remaining handwritten API route branches in `pack_api_server.py`

## P1

- replace allowlisted legacy defaultspack HTTP block routes with direct function boundaries
- retire `defaults.*` compatibility aliases where downstream callers no longer need them
- tighten defaultspack domain boundary policy from baseline capture toward intentional architecture limits

## P2

- continue clarifying unit execution isolation modes, especially container/sandbox boundaries
- keep update/apply flows moving toward explicit capability ownership
- trim residual transport/runtime compatibility shims once replacement paths are stable
- continue splitting `AmbientTriggerPanel.tsx` state/effects into smaller ambient hooks after the hand-tracker, routing, storage, and bridge seams are stable
- keep the PR #347 macOS ambient smoke checklist as a manual release gate until it has automated coverage: first mic/camera grant, denial and re-grant, window close/reopen, camera disconnect, finger recording dispatch, and approval gesture audit-failure stop
