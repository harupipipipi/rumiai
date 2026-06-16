# Known Debt

Last updated: 2026-06-06

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
