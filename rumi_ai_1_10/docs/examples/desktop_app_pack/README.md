<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](../../i18n/ja/examples/desktop_app_pack/README.md) | [KR](../../i18n/ko/examples/desktop_app_pack/README.md) | [CN](../../i18n/zh-cn/examples/desktop_app_pack/README.md)
<!-- docs-i18n-links:end -->

# Desktop App Pack

This is a sample pack that uses Rumi AI OS's **desktop_app.execute** capability.
Start the app in a separate desktop window (tkinter).

Pack also serves as a template that developers can copy and modify.

---

## Directory structure

```
desktop_app_pack/
├── ecosystem.json   # Pack マニフェスト（desktop_app セクション付き）
├── app.py           # デスクトップアプリ（tkinter Hello World + Kernel API 通信）
└── README.md        # このファイル
```

---

## What is desktop_app.execute capability?

`desktop_app.execute` is a core capability of the Rumi AI OS that allows Packs to launch applications in **independent desktop windows**.

Unlike the front-end display within the Viewer (`viewer:display`):

1. `pack-shell` binary automates Kernel startup confirmation and token acquisition
2. Communicate with Kernel API through environment variables (`RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID`)
3. Any GUI framework can be used, such as tkinter, Qt, Electron, Tauri, etc.

The definition of capability is in `core_runtime/core_pack/core_desktop_capability/`.

---

## How to use

### 1. Build pack-shell

```bash
cd pack-shell
cargo build --release
```

### 2. Place the pack

Copy this directory to `ecosystem/`:

```bash
cp -r docs/examples/desktop_app_pack/ ecosystem/desktop_app_pack/
```

### 3. Start Kernel

```bash
python -m rumi_ai
```

When Kernel starts, it automatically scans `ecosystem/desktop_app_pack/ecosystem.json`.

### 4. Approve the pack

ecosystem packs require approval the first time (unlike core_packs, they are not automatically approved).
Please approve the pack from the Kernel API or management screen.

### 5. Get a Grant

`desktop_app.execute` Permission grant is required.
**Note**: `desktop_app.execute` is set to `dangerous: true`. Grant approval means permission for the desktop app to launch arbitrary processes on the host OS.

### 6. Start the app with pack-shell

```bash
pack-shell run desktop_app_pack \
  --command "python app.py" \
  --working-dir /path/to/desktop_app_pack \
  --api-token "$RUMI_API_TOKEN"
```

A tkinter window opens with connection information to the Kernel API and Health Check functionality.

---

## Explanation of ecosystem.json

```json
{
  "pack_id": "desktop_app_pack",
  "desktop_app": {
    "command": "python app.py",
    "window": {
      "title": "Desktop App Pack",
      "width": 600,
      "height": 400
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

| Field | Description |
|-----------|------|
| `desktop_app.command` | Command that pack-shell launches. `--command` Passed as argument |
| `desktop_app.requires_api_token` | Is `DesktopAppManager` treated as `RUMI_API_TOKEN` mandatory? The current state is always saved in `true` |
| `desktop_app.window.title` | Used for shortcut name/window title |
| `desktop_app.window.width/height` | Recommended window size (when reading on the app side) |
| `desktop_app.platforms` | Supported platforms |

---

## Kernel API communication

`app.py` contains a sample communication to the Kernel API.

```python
import json
from urllib.request import Request, urlopen

port = os.environ.get("RUMI_PORT", "8765")
url = f"http://127.0.0.1:{port}/health"
req = Request(url, headers={"Accept": "application/json"})
with urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(data)  # {"status": "ok"}
```

Environment variables set by pack-shell:

| Variable | Description |
|------|------|
| `RUMI_TOKEN` | Temporary token issued by Kernel |
| `RUMI_PORT` | Kernel API port number (default: 8765) |
| `RUMI_PACK_ID` | Target Pack ID |

---

## Customization Tips

- **Change GUI**: tkinter code in `app.py` can be replaced with Qt, wxPython, Electron, etc.
- **Add an API call**: You can call the Kernel API by setting `RUMI_TOKEN` in the `Authorization: Bearer` header
- **Change command**: You can change `desktop_app.command` of `ecosystem.json` to `"node app.js"` or `"./my_binary"`
- **token contract**: `RUMI_API_TOKEN` is required before activation via `DesktopAppManager`
- **Change Pack name**: Please change `pack_id` and `pack_identity` of `ecosystem.json`
- **Window settings**: You can change `title`, `width`, `height` of `desktop_app.window`

---

## Related documents

- [Pack Desktop App Development Guide](../../pack_desktop_app_guide.md)
- [Pack Development Guide](../../pack-development.md)
- [Multilingual Pack Development Guide](../../multilang_pack_guide.md)
- [pack-shell README](../../../../pack-shell/README.md)
