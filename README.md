<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](./i18n/ja/README.md) | [KR](./i18n/ko/README.md) | [CN](./i18n/zh-cn/README.md)
<!-- docs-i18n-links:end -->

# Rumi AI

Rumi AI is a modular AI runtime and tooling workspace.

The repository keeps the runtime implementation under `rumi_ai_1_10/`, while `rumi_ai/` provides a version-stable Python entrypoint. The canonical control panel frontend source lives in `rumi_viewer/frontend`; the kernel serves its built artifact at `/panel/`.

## Read This When...

| What I want to do | Where to read first | Supplements |
|---|---|---|
| I want to follow the document by purpose | [`rumi_ai_1_10/docs/README.md`](./rumi_ai_1_10/docs/README.md) | We will guide you in the reading order starting from "what you want to do" |
| I want to start it anyway | `Start` of [`README.md`](./README.md) | Only the shortest startup command is listed |
| I want to know the overall picture of runtime / kernel | [`rumi_ai_1_10/README.md`](./rumi_ai_1_10/README.md) | There is an explanation of the architecture and main directories |
| I want to understand the mechanism without reading the code | [`rumi_ai_1_10/docs/concepts/system-mechanism.md`](./rumi_ai_1_10/docs/concepts/system-mechanism.md) | You can follow the flow of startup, flow, approval, and grant in text |
| I want to check the operation first (tutorial) | [`rumi_ai_1_10/docs/tutorials/runtime-quickstart.md`](./rumi_ai_1_10/docs/tutorials/runtime-quickstart.md) | The shortest steps from `--health` to `/panel/` |
| I want to start `rumi_viewer` / I want to see how the viewer gets stuck | [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) | Summary of startup procedure, `401`, black screen, and relationship with `defaultspack` |
| I want to fix the viewer side | [`rumi_viewer/src-tauri/src/config.rs`](./rumi_viewer/src-tauri/src/config.rs) and [`rumi_viewer/src-tauri/src/kernel_manager.rs`](./rumi_viewer/src-tauri/src/kernel_manager.rs) | The viewer is the Tauri shell, and the Rust side is responsible for starting the kernel |
| I want to use pack / defaultspack | [`rumi_ai_1_10/ecosystem/defaultspack/README.md`](./rumi_ai_1_10/ecosystem/defaultspack/README.md) | This is the pack side implementation of chat, ai_client, tool, etc. |
| I want to know how to extend defaultspack's frontend | [`rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md`](./rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md) | This is the gateway for adding right bar, adding settings, extending chat renderer, and adding preview feed |
| I want to know how to handle API keys and secrets | Secrets section of [`rumi_ai_1_10/docs/operations.md`](./rumi_ai_1_10/docs/operations.md) | There is an explanation of `user_data/secrets/` and the API route |
| I want to know how to create a Pack | [`rumi_ai_1_10/docs/pack-development.md`](./rumi_ai_1_10/docs/pack-development.md) | We have summarized the manners of ecosystem.json, routes, and permissions |
| I want to know the concept of operation and auditing | [`rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`](./rumi_ai_1_10/docs/quality_pack/philosophy_memo.md) | I am organizing the assumptions for continuous development and regression confirmation |

## Repository Layout

- `rumi_ai_1_10/`: kernel/runtime/API/backend source tree
- `rumi_ai/`: version-stable Python entrypoint package
- `pack-shell/`: desktop pack launcher
- `rumi_viewer/`: desktop shell and control panel frontend source
- `rumi_mobile/`: Flutter iOS/Android app for trusted-LAN defaultspack access

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- Rust / Cargo (when touching `rumi_viewer`)
- Flutter SDK (when using `rumi_mobile`)

### Clone and install

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r rumi_ai_1_10/requirements.txt -r rumi_ai_1_10/requirements-dev.txt
pip install -e ./rumi_ai_1_10

cd rumi_viewer/frontend
npm install
cd ../..
```

## Start

```bash
source .venv/bin/activate
python -m rumi_ai --health
python -m rumi_ai
```

`--health` also checks system volume usage. If the `disk` probe is `DEGRADED` / `DOWN`, it may be due to a lack of free space rather than a code problem.

## Common Tasks

### Just shortcuts

If you have `just` installed, common checks are available from the repo root:

```bash
just -l
just tooling-test
just integrity
```

### Backend health check

```bash
python -m rumi_ai --health
```

### Runtime startup

```bash
python -m rumi_ai
```

### Viewer development

```bash
cd rumi_viewer/src-tauri
cargo tauri dev
```

The development viewer automatically detects `rumi_ai_1_10/` in the repo and starts the kernel.
After startup, proceed from `Open Defaultspack` of Home to `Defaultspack v2` UI selected by managed current pointer.
Please refer to [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) for a guide including how to get stuck at startup.

## Development

```bash
source .venv/bin/activate
cd rumi_ai_1_10
python -m pytest tests/test_capability_trust_store.py
```

## Quality Pack

See below for operational packs for continuous development, auditing, and regression confirmation:

- `rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`
- `rumi_ai_1_10/docs/quality_pack/claude_desktop_quality_pack.md`
- `rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh`

## HMAC Migration

```bash
python -m rumi_ai migrate-hmac
```

## Components

- `rumi_ai`: stable CLI and module entrypoint
- `rumi_ai_1_10`: kernel, runtime, API, backend, and docs
- `pack-shell`: launches desktop packs and brokers token/bootstrap flow
- `rumi_viewer`: viewer-side application shell and canonical panel frontend source
- `rumi_mobile`: mobile remote client for the bearer-auth Kernel Pack API

For architecture and runtime details, see [rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md).

For Codex OSS-inspired coding-tool conventions, see [AGENTS.md](./AGENTS.md) and
[rumi_ai_1_10/docs/codex_oss_reference.md](./rumi_ai_1_10/docs/codex_oss_reference.md).
