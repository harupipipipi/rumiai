<!-- docs-i18n-links:start -->
[EN](./pack_desktop_app_guide.md) | [JP](./i18n/ja/pack_desktop_app_guide.md) | [KR](./i18n/ko/pack_desktop_app_guide.md) | [CN](./i18n/zh-cn/pack_desktop_app_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Pack Desktop App Development Guide

Last updated: 2026-03-28

This document is a guide for developers to integrate **desktop apps** (applications that run in separate desktop windows) into Rumi AI OS Packs. It covers how to set up ecosystem.json, how to use pack-shell binaries, the security model, and shortcut generation.

---

## 1. What is Desktop App Pack?

### 1.1 Overview

Pack desktop apps allow applications to run in separate desktop windows through Rumi AI OS's **capability-based permission system**.

Unlike the `viewer:display` capability, which displays the frontend inside the Rumi Viewer (Tauri-based WebView UI), the `desktop_app.execute` capability launches the app in an **OS-native window**. You can use any GUI framework such as tkinter, Qt, Electron, Tauri, etc.

### 1.2 Architecture

```
ユーザー
  │
  ├── ショートカット / CLI
  │       │
  │       ▼
  │   pack-shell (Rust バイナリ)
  │       │
  │       ├─ 1. Kernel /health チェック
  │       ├─ 2. Kernel 未起動なら自動起動
  │       ├─ 3. POST /api/desktop/token でトークン取得
  │       ├─ 4. 環境変数 (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID) を設定
  │       └─ 5. アプリプロセスを起動
  │               │
  │               ▼
  │           デスクトップアプリ (Python, Node.js, etc.)
  │               │
  │               ▼
  │           Kernel API (localhost:8765) と通信
  │
  └── Rumi AI OS Kernel
          │
          ├── CapabilityGrantManager (Grant 検証)
          ├── DesktopAppManager (登録・ショートカット生成)
          └── POST /api/desktop/token (トークン発行)
```

### 1.3 No Favoritism Principle

Desktop app support is also implemented using the same pattern as other capabilities. `core_desktop_capability` is included in the Kernel as core_pack and manages `desktop_app.execute` permissions. Third-party packs need a grant to use this capability, just like any other capability.

---

## 2. Prerequisites

To develop and run the Desktop App Pack, you will need:

- Environment where **Rumi AI OS** can be installed and started
- **pack-shell binary** has been built (see build instructions below)
- **Python 3.11 or higher** (for sample apps. The app itself can be implemented in any language)

---

## 3. desktop_app section of ecosystem.json

To add desktop app functionality to your pack, add the `desktop_app` section to `ecosystem.json`.

### 3.1 Setting example

```json
{
  "pack_id": "my_desktop_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Desktop App",
    "description": "デスクトップアプリのサンプル Pack"
  },
  "desktop_app": {
    "command": "python app.py",
    "working_dir": "",
    "env": {},
    "capabilities": ["desktop_app.execute"],
    "window": {
      "title": "My Desktop App",
      "width": 800,
      "height": 600
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

### 3.2 Field list

| Field | Type | Required | Description |
|-----------|-----|------|------|
| `command` | string | ✅ | Start command. Passed to the app as the `--command` argument of pack-shell |
| `working_dir` | string | — | Working directory of the app. If empty string, Pack directory will be used |
| `env` | dict | — | Additional environment variables to pass to the app. `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID` are not necessary as pack-shell automatically configures them |
| `capabilities` | list | — | List of requested capabilities |
| `window` | dict | — | Window settings. Specify the app name with `title` (string) and the size with `width`/`height` (int). Also used for shortcut names |
| `platforms` | list | — | Supported platforms. Combination of `"darwin"`, `"win32"`, `"linux"` |

### 3.3 Schema validation

The Kernel's `PackImporter` validates the `desktop_app` section with the following rules:

- If `desktop_app` is present, it must be a dict
- `desktop_app.command` is required and must be a non-empty string
- `working_dir` must be string, `env` must be dict, `capabilities` must be list, `window` must be dict, and `platforms` must be list (all can be omitted)

If validation fails, a warning will be printed when importing the Pack, and the Pack will not be registered.

---

## 4. desktop_app.execute capability

### 4.1 Overview

`desktop_app.execute` is a capability provided by `core_desktop_capability` Pack. Controls starting, stopping, and checking the status of desktop apps.

### 4.2 manifest.json

```json
{
  "function_id": "execute",
  "description": "デスクトップアプリケーションを起動・管理する",
  "requires": ["desktop_app.execute"],
  "grant_config": {
    "permission_id": "desktop_app.execute",
    "dangerous": true,
    "allowed_packs": ["my_desktop_pack"],
    "max_token_lifetime": 3600
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "pack_id": {
        "type": "string",
        "description": "Pack ID whose desktop app to execute"
      },
      "action": {
        "type": "string",
        "description": "Action to perform: launch, stop, status",
        "default": "launch",
        "enum": ["launch", "stop", "status"]
      }
    },
    "required": ["pack_id"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "token": { "type": "string" },
      "port": { "type": "integer" },
      "expires_in": { "type": "integer" }
    },
    "required": ["token", "port", "expires_in"]
  },
  "calling_convention": "block"
}
```

### 4.3 dangerous flag

`desktop_app.execute` is set to `dangerous: true`. This means that the desktop app has high privileges because it launches arbitrary processes on the host OS. Unlike Docker-isolated Python Functions, desktop apps have direct access to the host's file system and network.

Therefore, users must explicitly authorize the `desktop_app.execute` grant when installing the Pack.

### 4.4 action

| action | description |
|--------|------|
| `launch` | Start the app and issue a token (default) |
| `stop` | Stop running apps |
| `status` | Returns the running status of the app |

---

## 5. How to use pack-shell

### 5.1 Build

```bash
cd pack-shell
cargo build --release
```

Build artifacts: `target/release/pack-shell`

Cross compilation:

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

### 5.2 CLI Reference

pack-shell has subcommands `run` and `version`.

#### run subcommand

```
pack-shell run <PACK_ID> --command <COMMAND> [OPTIONS]
```

| Arguments | Type | Required | Default | Description |
|------|-----|------|-----------|------|
| `<PACK_ID>` | Positional argument | ✅ | — | ID of the Pack to launch |
| `--command` | string | ✅ | — | Command to execute (e.g. `"python app.py"`) |
| `--api-token` | string | ✅ | Environment variables `RUMI_API_TOKEN` | Kernel API authentication token |
| `--port` | u16 | — | `8765` | Kernel API port number |
| `--kernel-cmd` | string | — | `"python -m rumi_ai"` | Command to start if Kernel is not started |
| `--timeout` | u64 | — | `60` | Timeout for waiting for Kernel startup (seconds) |
| `--working-dir` | string | — | None | App working directory |

#### version subcommand

```bash
pack-shell version
# 出力: pack-shell 0.1.0
```

### 5.3 Execution example

```bash
# 基本的な使い方
pack-shell run my_desktop_pack --command "python app.py" --working-dir /path/to/my_desktop_pack --api-token "$TOKEN"

# 全オプション指定
pack-shell run my_desktop_pack \
  --command "python app.py" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai" \
  --api-token "your-api-token" \
  --timeout 60 \
  --working-dir /path/to/workdir
```

### 5.4 Execution flow

pack-shell launches the desktop app as follows:

1. Check the operating status of Kernel with `GET /health`
2. If Kernel is not responding, start kernel with `--kernel-cmd` and poll health check (1 second interval, up to `--timeout`)
3. Get temporary token at `POST /api/desktop/token`
4. Set environment variables `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID` and start the app process
5. Wait for the app process to end and return the exit code

### 5.5 Environment variables

Environment variables read by pack-shell:

| Variable | Description |
|------|------|
| `RUMI_API_TOKEN` | Replacement of `--api-token`. CLI arguments take precedence |

Launching via `DesktopAppManager` is fixed to a contract that supplies `RUMI_API_TOKEN` as an environment variable.

Environment variables that pack-shell passes to the app:

| Variable | Description |
|------|------|
| `RUMI_TOKEN` | Temporary token issued by Kernel |
| `RUMI_PORT` | Kernel API port number |
| `RUMI_PACK_ID` | Target Pack ID |

---

## 6. API Reference

### 6.1 POST /api/desktop/token

Issue temporary tokens for desktop apps. `core_desktop_capability` API route provided by Pack.

#### Request

```json
{
  "pack_id": "my_desktop_pack"
}
```

| Field | Type | Required | Description |
|-----------|-----|------|------|
| `pack_id` | string | ✅ | Pack ID for which the token is issued |

#### Response (success)

```json
{
  "token": "abc-123-xyz",
  "port": 8765,
  "expires_in": 3600
}
```

| Field | Type | Description |
|-----------|-----|------|
| `token` | string | Short-term access token |
| `port` | integer | Kernel API port number (default: 8765) |
| `expires_in` | integer | Token expiration time (seconds; default: 3600) |

#### Response (Error)

```json
{
  "error": "desktop_app.execute not granted for pack: my_desktop_pack",
  "status_code": 403
}
```

| status_code | description |
|------------|------|
| 400 | `pack_id` unspecified or invalid |
| 403 | No Grant for `desktop_app.execute` |
| 500 | Internal error |
| 503 | Desktop capability handler unavailable |

---

## 7. Shortcut generation

### 7.1 DesktopAppManager

The `DesktopAppManager` classes in `desktop_app_manager.py` manage the lifecycle of Pack desktop apps.

#### Main methods

| Method | Description |
|--------|------|
| `register_app(pack_id, desktop_app_config, pack_dir)` | Register the Pack desktop app and generate platform-specific shortcuts |
| `unregister_app(pack_id)` | Unsubscribe and delete shortcuts |
| `launch_app(pack_id)` | Start a registered app |
| `stop_app(pack_id)` | Stop a running application with SIGTERM |
| `list_registered_apps()` | Return list of registered apps |

#### Return value of register_app

```json
{
  "success": true,
  "shortcut_path": "/Users/user/Applications/MyApp.app"
}
```

### 7.2 Platform shortcuts

`register_app` automatically generates platform-specific shortcuts:

| Platform | Format | Location |
|---------------|------|--------|
| macOS (`darwin`) | `.app` bundle (Info.plist + launch script) | `~/Applications/<AppName>.app` |
| Windows (`win32`) | `.lnk` Shortcut (generated with PowerShell) | `user_data/apps/<AppName>.lnk` |
| Linux | `.desktop` File | `~/.local/share/applications/rumi-<AppName>.desktop` |

The shortcut `AppName` is taken from `desktop_app.window.title` (or `pack_id` if unspecified).

### 7.3 Searching for pack-shell binaries

`DesktopAppManager` searches for pack-shell binaries in the following order:

1. Path specified in environment variable `RUMI_PACK_SHELL_PATH`
2. Search `pack-shell` from `PATH` in the system

If not found, `register_app` returns an error.

---

## 8. Security

### 8.1 Why is it dangerous?

`desktop_app.execute` is set to `dangerous: true` for the following reasons:

- Desktop apps run directly on the host OS (no Docker isolation)
- Can access the file system, network, and other processes
- Any command specified in the `command` field is executed.

### 8.2 The importance of user approval

Pack is designed with malicious intent. Users should be sure to check what programs the desktop app `command` launches before approving the grant.

### 8.3 Token expiration time

Tokens issued with `POST /api/desktop/token` expire after a short period of time (default 3600 seconds = 1 hour). `max_token_lifetime` is controlled by `grant_config`.

`allowed_packs` is fail-closed. Empty arrays `[]`, unspecified, or illegal types are not allowed by any Pack. You can specify `["*"]` for validation purposes where you need to explicitly allow all Packs, but in general you should list the Pack IDs you want to launch.

### 8.4 Recommendations

- Only install packs from trusted sources
- Check the contents of `desktop_app.command` before approving the grant
- For packs that are no longer needed, delete the shortcuts with `unregister_app`
- Set `allowed_packs` to allow grants only to specific packs

---

## 9. Development flow

### 9.1 Step by Step

1. **Develop an app**: Create a desktop app using any framework such as tkinter, Qt, Electron, etc.
2. **Supports environment variables**: Implement code to read `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID` and communicate with Kernel API within the app.
3. **Test with pack-shell**: Confirm operation with `pack-shell run <PACK_ID> --command "python app.py" --working-dir <DIR> --api-token <TOKEN>`
4. **Add desktop_app to ecosystem.json**: Set `command`, `window`, `platforms` etc.
5. **Install the Pack**: Place it in `ecosystem/` or import it with PackImporter
6. **Approve Grant**: Set the grant for `desktop_app.execute` in GrantManager
7. **Generate shortcuts**: Automatically generate platform-specific shortcuts with `register_app` of DesktopAppManager

### 9.2 Local development tips

You can also set environment variables manually and launch the app directly without using pack-shell:

```bash
export RUMI_TOKEN="dev-token-for-testing"
export RUMI_PORT="8765"
export RUMI_PACK_ID="my_desktop_pack"
python app.py
```

Once the Kernel is running, you can check the connection with `GET /health`:

```bash
curl http://localhost:8765/health
# {"status": "ok"}
```

---

## 10. Troubleshooting

### pack-shell cannot connect to Kernel

- Check if Kernel is running: `curl http://localhost:8765/health`
- Check if the port number is correct: Default is `8765`
- Check if the correct Kernel startup command is specified in `--kernel-cmd`

### 403 error when getting token

- Check if Grant of `desktop_app.execute` is set.
- Check if `pack_id` is correct
- Check if the API token (`--api-token` or `RUMI_API_TOKEN`) is valid

### Shortcut not generated

- Check if pack-shell binary is found: set `RUMI_PACK_SHELL_PATH` or add to `PATH`
- Check the return value of `register_app`: `{"success": false, "error": "..."}` contains an error message

### App does not start

- Check if `desktop_app.command` is the correct command: try executing it directly in the shell
- Check that `working_dir` points to the correct directory
- Check if the required dependent libraries are installed

### Can't open .app on macOS

- If blocked by gatekeeper: Allow from "System Preferences > Security & Privacy"
- Check if the launch script has execution permission: `chmod +x ~/Applications/MyApp.app/Contents/MacOS/launch`

---

## Related documents

- [Pack Development Guide](./pack-development.md) — Overview of Pack
- [Multilingual Pack Development Guide](./multilang_pack_guide.md) — How to develop Packs in languages other than Python
- [Sample code: Desktop App Pack](examples/desktop_app_pack/) — Desktop App Pack template
- [pack-shell README](../../pack-shell/README.md) — pack-shell binary details
