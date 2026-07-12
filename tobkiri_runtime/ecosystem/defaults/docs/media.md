# Media 機能ガイド

## 1. 概要

media モジュールは defaults の `domain/media/` に配置されるドメインコードであり、画像操作・ドキュメントパース・クリップボード操作・スクリーンショットの handler を提供する。マルチモーダル AI 連携のための前処理・後処理を担う。


## 2. 画像操作

### defaults.media.image_read

画像ファイルを読み取り、メタデータと base64 データを返す。

権限: `media.image.read`

input_data:
```json
{
  "path": "screenshots/page.png",
  "resize": null,
  "format": null
}
```

`resize` で `{"width": 800, "height": 600}` を指定するとリサイズして返す。`format` で `"jpeg"` / `"png"` / `"webp"` を指定すると変換する。

戻り値:
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

画像に変換処理を適用する。

権限: `media.image.transform`

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

`output_path` を指定するとファイルに保存。省略すると base64 で返す。

戻り値:
```json
{
  "data": "base64...",
  "media_type": "image/jpeg",
  "width": 400,
  "height": 300,
  "size_bytes": 35000
}
```


## 3. ドキュメントパース

### defaults.media.doc_parse

PDF・Word・PowerPoint 等のドキュメントファイルからテキストを抽出する。

権限: `media.document.parse`

input_data:
```json
{
  "path": "docs/report.pdf",
  "pages": null,
  "extract_images": false,
  "ocr": false
}
```

`pages` で `[1, 2, 3]` を指定すると特定ページのみ。`extract_images` が true で画像も抽出。`ocr` が true で OCR を適用。

戻り値:
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


## 4. クリップボード操作

### defaults.media.clipboard_read

システムクリップボードの内容を読み取る。

権限: `media.clipboard.read`

input_data:
```json
{}
```

戻り値:
```json
{
  "content_type": "text",
  "text": "クリップボードのテキスト...",
  "image": null
}
```

画像がクリップボードにある場合:
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

システムクリップボードに書き込む。

権限: `media.clipboard.write`

input_data:
```json
{
  "content_type": "text",
  "text": "コピーするテキスト",
  "image": null
}
```

戻り値:
```json
{
  "success": true,
  "content_type": "text"
}
```


## 5. スクリーンショット

### defaults.media.screenshot

画面のスクリーンショットを取得する。

権限: `media.screenshot`

input_data:
```json
{
  "target": "screen",
  "screen_index": 0,
  "region": null,
  "format": "png"
}
```

`target` は `"screen"`（画面全体）または `"window"`（アクティブウィンドウ）。`region` で `{"x": 0, "y": 0, "width": 800, "height": 600}` を指定すると部分キャプチャ。

戻り値:
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
