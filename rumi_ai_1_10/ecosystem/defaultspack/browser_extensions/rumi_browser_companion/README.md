<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](./i18n/ja/README.md) | [KR](./i18n/ko/README.md) | [CN](./i18n/zh-cn/README.md)
<!-- docs-i18n-links:end -->

# Rumi Browser Companion

`Rumi Browser Companion` is a Manifest V3 Chromium extension that lets Rumi drive the user's real browser session through a local bridge. It is designed to complement the existing `browser_use` and `computer_use` tools:

- `computer_use` / `browser_computer`: visible-window, computer-use style control
- `browser_companion`: DOM-aware browser control inside the user's signed-in browser profile

This gives Rumi a "computer use + browser use" path where the model can inspect DOM state, select between connected browsers, and operate with the user's live cookies and sessions.

## Files

- `manifest.json`: extension manifest
- `background.js`: bridge polling, browser metadata, tab operations, capture orchestration
- `content_script.js`: DOM snapshots and element-level actions
- `options.html`, `options.css`, `options.js`: local bridge configuration UI

## Install

1. Open a Chromium-based browser such as Chrome, Edge, Brave, or Vivaldi.
2. Open the browser's extensions page and enable developer mode.
3. Choose "Load unpacked" and select this folder:

   `<repo>/rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/rumi_browser_companion`

4. In Rumi, call `browser_companion` with `action: "bridge.pairing"` to get the pairing token and candidate server URLs.
5. Open the extension options page and paste:

   - `Server URL` such as `http://127.0.0.1:8766`
   - `Pairing Token`

6. Click `Poll Bridge Now` to confirm the extension can connect.

## Bridge API

The extension talks to these local endpoints:

- `POST {serverUrl}/api/tools/browser-companion/bridge/poll`
- `POST {serverUrl}/api/tools/browser-companion/bridge/result`

`poll` request body:

```json
{
  "pairing_token": "example-token",
  "client": {
    "client_id": "uuid",
    "label": "My Edge Companion",
    "browser_name": "Microsoft Edge",
    "browser_version": "136.0.0.0",
    "extension_version": "0.1.0",
    "platform": "Win32",
    "user_agent": "...",
    "active_tab_id": 123,
    "tabs": [
      {
        "id": 123,
        "windowId": 1,
        "active": true,
        "title": "Example",
        "url": "https://example.com",
        "status": "complete"
      }
    ]
  }
}
```

`poll` response body:

```json
{
  "status": "ok",
  "data": {
    "accepted": true,
    "client_id": "uuid",
    "command": {
      "command_id": "cmd_123",
      "action": "page.snapshot",
      "payload": {
        "tab_id": 123,
        "include_capture": true,
        "limit": 200
      }
    }
  }
}
```

`result` request body:

```json
{
  "pairing_token": "example-token",
  "client_id": "uuid",
  "results": [
    {
      "command_id": "cmd_123",
      "ok": true,
      "result": {
        "snapshot": {
          "url": "https://example.com",
          "title": "Example",
          "nodes": []
        }
      }
    }
  ]
}
```

## Supported Actions

- `browser.tabs`
- `browser.select_tab`
- `page.navigate`
- `page.snapshot`
- `page.capture`
- `page.click`
- `page.type`
- `page.press`
- `page.scroll`
- `page.extract`

## Safety Notes

- This extension can inspect and act on pages in the user's real browser profile.
- Only pair it with a local Rumi server you control.
- Do not share the pairing token.
- Capture and tab selection may foreground the browser tab.
- DOM actions are best-effort and may not work on all pages.

## Notes

- The extension uses the user's real browser profile, so authenticated pages work with the user's existing cookies and sessions.
- DOM snapshots and element actions can target tabs that already have the content script loaded.
- Visible tab capture still depends on the browser's active visible tab, so capture requests may activate the target tab.
