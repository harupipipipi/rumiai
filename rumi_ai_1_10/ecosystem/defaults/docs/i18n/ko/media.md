<!-- docs-i18n-links:start -->
[EN](../../media.md) | [JP](../ja/media.md) | [KR](./media.md) | [CN](../zh-cn/media.md)
<!-- docs-i18n-links:end -->

# 미디어 기능 안내

## 1. 개요

미디어 모듈은 기본값의 `domain/media/`에 배치된 도메인 코드이며 이미지 조작, 문서 구문 분석, 클립보드 조작 및 스크린샷을 위한 핸들러를 제공합니다. 멀티모달 AI 협업을 위한 전처리와 후처리를 담당합니다.


## 2. 이미지 조작

### defaults.media.image_read

이미지 파일을 읽고 메타데이터 및 base64 데이터를 반환합니다.

권한: `media.image.read`

입력_데이터:
```json
{
  "path": "screenshots/page.png",
  "resize": null,
  "format": null
}
```

`resize`에 `{"width": 800, "height": 600}`을 지정하면 크기가 조정되어 반환됩니다. `"jpeg"` / `"png"` / `"webp"`가 `format`에 지정된 경우 변환됩니다.

반환 값:
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

이미지에 변형을 적용합니다.

권한: `media.image.transform`

입력_데이터:
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

`output_path`을 지정한 경우 파일에 저장합니다. 생략하면 base64가 반환됩니다.

반환 값:
```json
{
  "data": "base64...",
  "media_type": "image/jpeg",
  "width": 400,
  "height": 300,
  "size_bytes": 35000
}
```


## 3. 문서 파싱

### defaults.media.doc_parse

PDF, Word, PowerPoint 등의 문서 파일에서 텍스트를 추출합니다.

권한: `media.document.parse`

입력_데이터:
```json
{
  "path": "docs/report.pdf",
  "pages": null,
  "extract_images": false,
  "ocr": false
}
```

`pages`에 `[1, 2, 3]`을 지정하면 특정 페이지만 표시됩니다. `extract_images`가 true이면 이미지도 추출됩니다. `ocr`이 true이고 OCR이 적용됩니다.

반환 값:
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


## 4. 클립보드 작업

### defaults.media.clipboard_read

시스템 클립보드의 내용을 읽습니다.

권한: `media.clipboard.read`

입력_데이터:
```json
{}
```

반환 값:
```json
{
  "content_type": "text",
  "text": "クリップボードのテキスト...",
  "image": null
}
```

이미지가 클립보드에 있는 경우:
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

시스템 클립보드에 씁니다.

권한: `media.clipboard.write`

입력_데이터:
```json
{
  "content_type": "text",
  "text": "コピーするテキスト",
  "image": null
}
```

반환 값:
```json
{
  "success": true,
  "content_type": "text"
}
```


## 5. 스크린샷

### defaults.media.screenshot

화면의 스크린샷을 찍습니다.

권한: `media.screenshot`

입력_데이터:
```json
{
  "target": "screen",
  "screen_index": 0,
  "region": null,
  "format": "png"
}
```

`target`은 `"screen"`(전체 화면) 또는 `"window"`(활성 창)입니다. `{"x": 0, "y": 0, "width": 800, "height": 600}`가 `region`에 지정된 경우 부분 캡처.

반환 값:
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
