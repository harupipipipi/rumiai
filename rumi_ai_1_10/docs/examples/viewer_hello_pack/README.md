<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](../../i18n/ja/examples/viewer_hello_pack/README.md) | [KR](../../i18n/ko/examples/viewer_hello_pack/README.md) | [CN](../../i18n/zh-cn/examples/viewer_hello_pack/README.md)
<!-- docs-i18n-links:end -->

# Viewer Hello Pack

This is a sample pack that uses Rumi AI OS's **viewer:display** capability.
Display the Hello World frontend inside Rumi Viewer.

Pack also serves as a template that developers can copy and modify.

---

## Directory structure

```
viewer_hello_pack/
├── ecosystem.json   # Pack マニフェスト
├── web/
│   ├── index.html   # フロントエンド（Hello World ページ）
│   └── app.js       # Kernel API 通信サンプル
└── README.md        # このファイル
```

---

## What is viewer:display capability?

`viewer:display` is one of the core capabilities of Rumi AI OS, and is the permission for Pack to display the front end in Rumi Viewer (Tauri-based desktop UI).

Packs with this capability:

1. Static files in the directory specified in `web_mount` are distributed from the Viewer.
2. Kernel issues a short-term token and Viewer authenticates with that token
3. Kernel API (`localhost:8765`) can be called from the front end

The definition of capability is in `core_runtime/core_pack/core_viewer_capability/`.

---

## How to use

### 1. Place the pack

Copy this directory to `ecosystem/`:

```bash
cp -r docs/examples/viewer_hello_pack/ ecosystem/viewer_hello_pack/
```

### 2. Start Kernel

```bash
python -m rumi_ai
```

When Kernel starts, it automatically scans `ecosystem/viewer_hello_pack/ecosystem.json`.

### 3. Approve the pack

ecosystem packs require approval the first time (unlike core_packs, they are not automatically approved).
Please approve the pack from the Kernel API or management screen.

### 4. Get a Grant

`viewer.display` Permission grant is required.
Configure the grant as follows:

- Added `viewer.display` Grant to `viewer_hello_pack` to Kernel GrantManager
- Once the grant is set, the frontend will be visible through the viewer:display function

### 5. Display with Viewer

When you start Rumi Viewer, you will see the front end of approved/granted packs.
`web/index.html` is rendered in the Viewer and the communication demo with the Kernel API works.

---

## Explanation of ecosystem.json

```json
{
  "pack_id": "viewer_hello_pack",
  "capabilities": ["viewer.display"],
  "web_mount": "web"
}
```

| Field | Description |
|-----------|------|
| `capabilities` | List of requested capabilities. Specifying `viewer.display` enables Viewer display |
| `web_mount` | Directory to serve static files. Path relative to Pack root |

---

## Kernel API communication

`web/app.js` contains a fetch sample to the Kernel API.

```javascript
fetch("http://localhost:8765/api/health", {
  method: "GET",
  headers: { "Accept": "application/json" }
})
  .then(response => response.json())
  .then(data => console.log(data));
```

The default port for the Kernel API is `8765`.

---

## Customization Tips

- **Change UI**: Edit HTML/CSS of `web/index.html`. It is also possible to add external CSS frameworks
- **Add API call**: Add new fetch call to `web/app.js`
- **Add Functions**: You can also implement backend processing by adding Functions to the `functions` section of `ecosystem.json` and the `functions/` directory
- **Multiple Pages**: Add pages to the `web/` directory and support them with SPA routing and multiple HTML files
- **Change Pack name**: Please change `pack_id` and `pack_identity` of `ecosystem.json`

---

## Related documents

- [Pack Development Guide](../../pack-development.md)
- [Multilingual Pack Development Guide](../../multilang_pack_guide.md)
- [core_viewer_capability](../../../core_runtime/core_pack/core_viewer_capability/)
