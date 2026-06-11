<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](./i18n/ja/README.md) | [KR](./i18n/ko/README.md) | [CN](./i18n/zh-cn/README.md)
<!-- docs-i18n-links:end -->

# pack-shell

Helper binaries for launching Pack desktop apps.

## Overview

pack-shell automates the following flow:

1. Check the /health endpoint of the Kernel
2. If Kernel is not started, it will start automatically.
3. Get the authentication token at /api/desktop/token
4. Set environment variables (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID) and start the app

## Build

```bash
cd pack-shell
cargo build --release
```

Build artifacts: `target/release/pack-shell`

## How to use

```bash
# 基本的な使い方
pack-shell run <PACK_ID> --command "python app.py" --api-token "$TOKEN"

# 全オプション指定
pack-shell run my-pack-123 \
  --command "python app.py" \
  --api-token "your-api-token" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai" \
  --timeout 60 \
  --working-dir /path/to/workdir

# バージョン表示
pack-shell version
```

## Startup flow

```
pack-shell run
    │
    ▼
GET /health ──── OK ───────────────┐
    │                              │
    │ (timeout/error)              │
    ▼                              │
Start Kernel subprocess            │
    │                              │
    ▼                              │
Poll /health (1s interval)         │
    │                              │
    ▼ (healthy)                    │
    ◄──────────────────────────────┘
    │
    ▼
POST /api/desktop/token
    │
    ▼
Set env vars (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID)
    │
    ▼
Spawn app subprocess (--command)
    │
    ▼
Wait for app exit → return exit code
```

## Environment variables

### Input (read by pack-shell)

| Variable | Description | Notes |
|------|------|------|
| RUMI_API_TOKEN | API authentication token | --api-token alternative |

A desktop app launched from `DesktopAppManager` is a contract that receives `RUMI_API_TOKEN` as an environment variable.

### Output (pass to app)

| Variable | Description |
|------|------|
| RUMI_TOKEN | Temporary token for desktop |
| RUMI_PORT | Kernel API port |
| RUMI_PACK_ID | Target Pack ID |

## Cross build

```bash
# macOS (Apple Silicon)
cargo build --release --target aarch64-apple-darwin

# macOS (Intel)
cargo build --release --target x86_64-apple-darwin

# Windows
cargo build --release --target x86_64-pc-windows-msvc

# Linux
cargo build --release --target x86_64-unknown-linux-gnu
```
