# defaultspack Integration TODO

## Goal

defaultspack is a Rumi-provided pack desktop app. Its frontend must stay a replaceable shell, not a hardwired owner of backend components.

## Principles

- Parts are declared as data. The frontend receives part contracts and renders what it understands.
- Components decide how parts are used by contributing manifests/config, not by editing React for every new component.
- Backend capability/component names stay behind `/api/ui/*` contracts.
- User overlays can replace or extend default parts through `user_data/shared/frontend_extensions/*.ui.json`.
- UI can be thrown away later; contracts, manifests, routes, and icon asset paths should survive that rewrite.

## Current Slice

- [x] Move the Rumi favicon into defaultspack-owned assets.
- [x] Expose the icon through UI surface config instead of hardcoding it in React.
- [x] Add defaultspack `desktop_app` metadata to `ecosystem.json`.
- [x] Add a small desktop launcher that opens the defaultspack HTTP surface.
- [x] Register `/api/ui/catalog`, `/api/ui/settings`, and `/api/ui/conversations/{id}/preview`.
- [x] Add fallback HTTP routes for standalone mode.
- [x] Add UI surface config slots for parts and component bindings.
- [x] Keep frontend access through typed API contracts.
- [x] Add shell layout / shell renderer contracts to the UI catalog.
- [x] Let `user_data/shared/frontend_shell.json` override shell layout without editing React.
- [x] Add schema-bearing parts for app chrome, history, chat, preview, sidebar, and settings.
- [x] Gate visible React regions through the shell layout contract.

## Next Slice

- [ ] Split each visible React area into its own small renderer module under `webapp/src/renderers/`.
- [ ] Add lazy custom renderer loading for trusted local bundles, with error boundaries and fallback renderers.
- [ ] Add validation diagnostics for malformed `parts`, `component_bindings`, `shell_layout`, and `shell_renderers`.
- [ ] Add explicit schemas for tool timelines, plan steps, approvals, attachments, and audio payloads beyond the first preview contract.
- [ ] Wire the viewer / Grant flow to launch packs with `desktop_app.execute`.
- [ ] Add a native webview wrapper if defaultspack should open outside the system browser.
