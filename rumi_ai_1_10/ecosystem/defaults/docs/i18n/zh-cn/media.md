<!-- docs-i18n-links:start -->
[EN](../../media.md) | [JP](../ja/media.md) | [KR](../ko/media.md) | [CN](./media.md)
<!-- docs-i18n-links:end -->

# 媒体功能指南

## 1. 概述

媒体模块是放置在默认值`domain/media/`中的域代码，并提供图像操作、文档解析、剪贴板操作和屏幕截图的处理程序。负责多模态人工智能协作的预处理和后处理。


## 2. 图像处理

### defaults.media.image_read

读取图像文件并返回元数据和 Base64 数据。

权限：`media.image.read`

输入数据：
```json
{
  "path": "screenshots/page.png",
  "resize": null,
  "format": null
}
```

如果在`resize`中指定了`{"width": 800, "height": 600}`，它将被调整大小并返回。当`"jpeg"`/`"png"`/`"webp"`在`format`中指定时进行转换。

返回值：
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

对图像应用变换。

权限：`media.image.transform`

输入数据：
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

如果指定`output_path`，则保存到文件。如果省略，则返回 base64。

返回值：
```json
{
  "data": "base64...",
  "media_type": "image/jpeg",
  "width": 400,
  "height": 300,
  "size_bytes": 35000
}
```


## 3.文档解析

### defaults.media.doc_parse

从 PDF、Word 和 PowerPoint 等文档文件中提取文本。

权限：`media.document.parse`

输入数据：
```json
{
  "path": "docs/report.pdf",
  "pages": null,
  "extract_images": false,
  "ocr": false
}
```

如果在`pages`中指定了`[1, 2, 3]`，则仅显示特定页面。如果`extract_images`为真，图像也会被提取。 `ocr` 为真且 OCR 已应用。

返回值：
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


## 4.剪贴板操作

### defaults.media.clipboard_read

读取系统剪贴板的内容。

权限：`media.clipboard.read`

输入数据：
```json
{}
```

返回值：
```json
{
  "content_type": "text",
  "text": "クリップボードのテキスト...",
  "image": null
}
```

如果图像位于剪贴板上：
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

写入系统剪贴板。

权限：`media.clipboard.write`

输入数据：
```json
{
  "content_type": "text",
  "text": "コピーするテキスト",
  "image": null
}
```

返回值：
```json
{
  "success": true,
  "content_type": "text"
}
```


## 5. 截图

### defaults.media.screenshot

截取屏幕截图。

权限：`media.screenshot`

输入数据：
```json
{
  "target": "screen",
  "screen_index": 0,
  "region": null,
  "format": "png"
}
```

`target` 是`"screen"`（全屏）或`"window"`（活动窗口）。当`{"x": 0, "y": 0, "width": 800, "height": 600}`在`region`中指定时部分捕获。

返回值：
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
