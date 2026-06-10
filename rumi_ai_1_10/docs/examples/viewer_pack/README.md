<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](../../i18n/ja/examples/viewer_pack/README.md) | [KR](../../i18n/ko/examples/viewer_pack/README.md) | [CN](../../i18n/zh-cn/examples/viewer_pack/README.md)
<!-- docs-i18n-links:end -->

# Viewer Example Pack

A minimal example of a Pack that uses the `viewer:display` capability to display a frontend in Rumi Viewer.

## Overview

This Pack shows:

- `viewer.display` How to declare capability (`manifest.json`, `requires` and `vocab_aliases`)
- Grant settings by `grant_config`
- Frontend delivery with `web_mount`
- Function stub for `calling_convention: "block"`

## Directory structure

```
viewer_pack/
├── ecosystem.json                    # Pack 定義（web_mount, functions）
├── functions/
│   └── request_display/
│       ├── manifest.json             # viewer.display capability 宣言
│       └── main.py                   # Function スタブ（block）
├── web/
│   ├── index.html                    # Pack フロントエンド
│   └── style.css                     # スタイル
└── README.md                         # このファイル
```

## Role of each file

### ecosystem.json

Pack's manifest. Define `pack_id`, `metadata`, `web_mount`, `functions`.
The `web_mount` field delivers the contents of the `web/` directory within the Rumi Viewer.

### functions/request_display/manifest.json

`viewer.display` Detailed declaration of capability. The following fields are important:

- **`requires`**: `["viewer.display"]` — capability required by this Function
- **`vocab_aliases`**: `["viewer.display"]` — Used for alias resolution in FunctionRegistry
- **`grant_config`**: Grant settings (`allowed_packs`, `max_token_lifetime`)
- **`calling_convention`**: `"block"` — Executed via Kernel's DI handler

### functions/request_display/main.py

This is a stub for `calling_convention: "block"`. Kernel DI handler at runtime
(`handle_display`), so this file is never executed directly.
Exists for the integrity of the Pack structure.

### web/index.html, web/style.css

This is the front end for Pack. Loaded inside Rumi Viewer's sandbox WebView.
I don't use CDN and write it in plain HTML/CSS.

## How viewer:display capability works

1. Pack requests `viewer.display` capability
2. `capability_executor` resolved by `FunctionRegistry.resolve_by_alias("viewer.display")`
3. If `grant_config` is set, `capability_grant_manager` checks Grant
4. `calling_convention: "block"` → Kernel DI handler (`handle_display`) executes
5. Token and `web_mount_url` will be returned
6. Rumi Viewer loads `web_mount_url` into sandbox WebView

## Obtaining a Grant

This pack requires a grant to use the `viewer.display` capability.
The Grant is administered by `capability_grant_manager`.

- **`allowed_packs`**: If empty array `[]`, allow requests from all Packs
- **`max_token_lifetime`**: Maximum token expiration time (seconds)

For more information on how grants work, see [Pack Development Guide Section 6](../../pack-development.md).

## Related documents

- [Pack Development Guide](../../pack-development.md) — Details of Pack structure, life cycle, and capabilities
- [Multilingual Pack Development Guide](../../multilang_pack_guide.md) — How to develop Packs in languages other than Python
