<!-- docs-i18n-links:start -->
[EN](../../media.md) | [JP](./media.md) | [KR](../ko/media.md) | [CN](../zh-cn/media.md)
<!-- docs-i18n-links:end -->

# メディア機能ガイド

## 1. 概要

メディア モジュールは、デフォルトの `domain/media/` に配置されるドメイン コードであり、画像操作、ドキュメント解析、クリップボード操作、およびスクリーンショット用のハンドラーを提供します。マルチモーダル AI コラボレーションの前処理と後処理を担当します。


## 2. 画像操作

### defaults.media.image_read

画像ファイルを読み取り、メタデータとbase64データを返します。

権限: `media.image.read`

入力データ:
```json
{
  "path": "screenshots/page.png",
  "resize": null,
  "format": null
}
```

`resize`に`{"width": 800, "height": 600}`を指定した場合はリサイズして返却します。 `format`に`"jpeg"` / `"png"` / `"webp"`を指定した場合に変換します。

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

画像に変換を適用します。

権限: `media.image.transform`

入力データ:
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

`output_path`を指定した場合はファイルに保存します。省略した場合は、base64 が返されます。

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


## 3. 文書の解析

### defaults.media.doc_parse

PDF、Word、PowerPoint などのドキュメント ファイルからテキストを抽出します。

権限: `media.document.parse`

入力データ:
```json
{
  "path": "docs/report.pdf",
  "pages": null,
  "extract_images": false,
  "ocr": false
}
```

`pages`に`[1, 2, 3]`を指定すると、特定のページのみが表示されます。 `extract_images` が true の場合、画像も抽出されます。 `ocr` が true で、OCR が適用されます。

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


## 4. クリップボードの操作

### defaults.media.clipboard_read

システムのクリップボードの内容を読み取ります。

権限: `media.clipboard.read`

入力データ:
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

システムのクリップボードに書き込みます。

権限: `media.clipboard.write`

入力データ:
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

### デフォルト.メディア.スクリーンショット

画面のスクリーンショットを撮ります。

権限: `media.screenshot`

入力データ:
```json
{
  "target": "screen",
  "screen_index": 0,
  "region": null,
  "format": "png"
}
```

`target` は、`"screen"` (フルスクリーン) または `"window"` (アクティブウィンドウ) です。 `region`で`{"x": 0, "y": 0, "width": 800, "height": 600}`を指定した場合の部分キャプチャ。

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
