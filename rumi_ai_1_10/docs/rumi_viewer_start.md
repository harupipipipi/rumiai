<!-- docs-i18n-links:start -->
[EN](./rumi_viewer_start.md) | [JP](./i18n/ja/rumi_viewer_start.md) | [KR](./i18n/ko/rumi_viewer_start.md) | [CN](./i18n/zh-cn/rumi_viewer_start.md)
<!-- docs-i18n-links:end -->

# rumi_viewer Start Guide

`rumi_viewer` is a desktop shell made by Tauri. During development startup, it automatically detects `rumi_ai_1_10/` in the repo, starts the Python kernel, and connects to the panel UI.
The control panel frontend source is owned by `rumi_viewer/frontend`, and the kernel delivers built artifacts as `rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web` to `/panel/`.

## When to read this

- I want to start viewer as soon as possible
- viewer cannot find kernel and stops
- The panel opens, but the screen transition is broken.
- I want to follow the startup path around the frontend / panel of `defaultspack`

## Shortest startup procedure

Run the following in the repo root:

```bash
cd rumi_viewer/frontend
npm install
cd ..
cargo tauri dev
```

From the second time onwards, if you have `rumi_viewer/frontend/node_modules` left, you can start it by simply doing the following:

```bash
cd rumi_viewer
cargo tauri dev
```

During development startup, the viewer automatically does the following:

1. Detect `rumi_ai_1_10/` in repo
2. Prepare `~/Library/Application Support/dev.rumiai.app/venv`
3. Start the kernel with `python -m app`
4. Bootstrap to `http://127.0.0.1:8765/panel/`
5. Press `Open Defaultspack` from viewer to open independent UI of `defaultspack`

## Approval flow during development

- Detecting repo checkout does not alone enable pack auto-approval
- `RUMI_ENVIRONMENT=development` is passed to the kernel as a development environment
- Automatic approval for development is enabled only when the viewer is started with `RUMI_AUTO_APPROVE_LOCAL=true` specified.

Example:

```bash
cd rumi_viewer
RUMI_AUTO_APPROVE_LOCAL=true cargo tauri dev
```

In a normal development launch without this opt-in, the modified pack remains pending re-approval.

## What it looks like when it starts up

- Tauri window will open after normal startup
- In the initial state, `/health` may return `needs_setup: true`, in which case it starts from the setup screen
- After setup is complete, you will be redirected to panel UI
- If you press `Open Defaultspack` from Home on the panel, the viewer will launch the browser UI of `defaultspack`

## Relationship with defaultspack

- The viewer opens directly in the kernel control panel (`/panel/`)
- The frontend source is on the viewer side, but the delivery route is still the kernel's `/panel/`
- `defaultspack` itself is loaded as a component from the kernel
- Independent HTTP frontend for `defaultspack` is `DEFAULTS_HTTP_PORT` default value `8766` but is separate from the viewer's initial conduit
- When starting development (`cargo tauri dev`), `rumi_ai_1_10/ecosystem/defaultspack/` included in the repo will be opened first.
- Distribution/bundle launches see `rumi_home/user_data/packs/defaultspack/current.json` and also refer to `app_data_dir/user_data/packs/defaultspack/current.json` for migration compatibility
- Therefore, if the setup/updated `Defaultspack v2` is switched to a managed pack, you can open the entity from the distributed viewer.

## Common clogs

### `Kernel directory not found`

Either the viewer only sees `app/` in the bundle, or it cannot detect repo checkout. Please start development under the repo root.

### `panel bootstrap returned 401 Unauthorized`

The bootstrap secret may be misaligned, or an old kernel may be grabbing port `8765`. Check occupancy below.

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

### When you press Home etc., it becomes pitch black.

panel frontend assumes `basename="/panel"`. If you add `/panel/...` twice in a link or `navigate()`, it will jump to `/panel/panel` and cause a route mismatch. The routes on the frontend side should be basename relative like `/`, `/packs`, `/flows`, `/settings`.

## Confirm command

Check if the kernel is running:

```bash
curl http://127.0.0.1:8765/health
```

Check if the defaultspack independent frontend is running:

```bash
curl http://127.0.0.1:8766/api/health
```

## Related files

- `rumi_viewer/src-tauri/src/config.rs`
- `rumi_viewer/src-tauri/src/kernel_manager.rs`
- `rumi_viewer/src-tauri/src/lib.rs`
- `rumi_viewer/frontend/src/App.tsx`
- `rumi_viewer/frontend/src/lib/routes.ts`
