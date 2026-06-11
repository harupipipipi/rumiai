<!-- docs-i18n-links:start -->
[EN](./media.md) | [JP](./i18n/ja/media.md) | [KR](./i18n/ko/media.md) | [CN](./i18n/zh-cn/media.md)
<!-- docs-i18n-links:end -->

# Media feature guide

## 1. Overview

The media module is a domain code placed in `domain/media/` of defaults and provides handlers for image manipulation, document parsing, clipboard manipulation, and screenshots. Responsible for pre-processing and post-processing for multimodal AI collaboration.


## 2. Image manipulation

### defaults.media.image_read

Reads an image file and returns metadata and base64 data.

Permissions: `media.image.read`

input_data:
```json
{
  "path": "screenshots/page.png",
  "resize": null,
  "format": null
}
```

If `{"width": 800, "height": 600}` is specified in `resize`, it will be resized and returned. Convert when `"jpeg"` / `"png"` / `"webp"` is specified in `format`.

Return value:
```json
{
  "data": "base64...",
  "media_type": "image/png",
  "width": 1920,
  "height": 1080,
  "size_bytes": 245000,
  "path": "screenshots/page.png"
}
```

### defaults.media.image_transform

Apply transformations to images.

Permissions: `media.image.transform`

input_data:
```json
{
  "source": "base64... or path",
  "operations": [
    {"type": "resize", "width": 800, "height": 600},
    {"type": "crop", "x": 0, "y": 0, "width": 400, "height": 300},
    {"type": "rotate", "degrees": 90},
    {"type": "format", "target": "jpeg", "quality": 85}
  ],
  "output_path": null
}
```

If `output_path` is specified, save to file. If omitted, base64 is returned.

Return value:
```json
{
  "data": "base64...",
  "media_type": "image/jpeg",
  "width": 400,
  "height": 300,
  "size_bytes": 35000
}
```


## 3. Document parsing

### defaults.media.doc_parse

Extract text from document files such as PDF, Word, and PowerPoint.

Permissions: `media.document.parse`

input_data:
```json
{
  "path": "docs/report.pdf",
  "pages": null,
  "extract_images": false,
  "ocr": false
}
```

If `[1, 2, 3]` is specified in `pages`, only specific pages will be displayed. If `extract_images` is true, images are also extracted. `ocr` is true and OCR is applied.

Return value:
```json
{
  "text": "ドキュメントの全文テキスト...",
  "pages": [
    {"page": 1, "text": "1ページ目のテキスト..."},
    {"page": 2, "text": "2ページ目のテキスト..."}
  ],
  "images": [],
  "metadata": {
    "title": "Report",
    "author": "Author Name",
    "page_count": 15,
    "format": "pdf"
  }
}
```


## 4. Clipboard operations

### defaults.media.clipboard_read

Read the contents of the system clipboard.

Permissions: `media.clipboard.read`

input_data:
```json
{}
```

Return value:
```json
{
  "content_type": "text",
  "text": "クリップボードのテキスト...",
  "image": null
}
```

If the image is on the clipboard:
```json
{
  "content_type": "image",
  "text": null,
  "image": {
    "data": "base64...",
    "media_type": "image/png",
    "width": 800,
    "height": 600
  }
}
```

### defaults.media.clipboard_write

Write to the system clipboard.

Permissions: `media.clipboard.write`

input_data:
```json
{
  "content_type": "text",
  "text": "コピーするテキスト",
  "image": null
}
```

Return value:
```json
{
  "success": true,
  "content_type": "text"
}
```


## 5. Screenshot

### defaults.media.screenshot

Take a screenshot of the screen.

Permissions: `media.screenshot`

input_data:
```json
{
  "target": "screen",
  "screen_index": 0,
  "region": null,
  "format": "png"
}
```

`target` is `"screen"` (full screen) or `"window"` (active window). Partial capture when `{"x": 0, "y": 0, "width": 800, "height": 600}` is specified in `region`.

Return value:
```json
{
  "data": "base64...",
  "media_type": "image/png",
  "width": 2560,
  "height": 1440,
  "size_bytes": 850000,
  "target": "screen"
}
```
