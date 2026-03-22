# rumi_launcher

Native launcher for **Rumi AI OS**. Written in Rust.

## Responsibilities

1. **Python environment bootstrap** — downloads python-build-standalone (PBS)
   and `uv`, creates a virtual-environment, and installs `requirements.txt`.
2. **Kernel process management** — starts the Kernel in the venv, monitors the
   process, and auto-restarts on exit code 42.
3. **System tray** — provides "Open Rumi AI", "Restart Kernel", and "Quit"
   menu items via the `tray-icon` crate.
4. **Health check** — polls `GET /health` on the Kernel HTTP port (default 8765).
5. **Update** — stub for Phase U.

## Building

```bash
# Debug build
cargo build

# Release build (optimised + stripped)
cargo build --release
```

## Dependencies

See `Cargo.toml`. Key crates:

| Crate | Purpose |
|-------|---------|
| `tray-icon` | System tray icon + menu |
| `reqwest` | HTTP client (blocking, rustls-tls) |
| `flate2` + `tar` | Archive extraction |
| `image` | PNG loading for tray icon |
| `anyhow` | Error handling |

## Directory layout (at runtime)

```text
{app_dir}/
├── rumi-launcher(.exe)
├── rumi_ai_1_10/       ← Python source tree
├── python/             ← PBS standalone Python
├── uv(.exe)            ← uv package manager
├── venv/               ← Python venv
├── user_data/
└── logs/
```
