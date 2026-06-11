<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](./README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# 루미 브라우저 컴패니언

`Rumi Browser Companion`은 Rumi가 로컬 브리지를 통해 사용자의 실제 브라우저 세션을 구동할 수 있게 해주는 Manifest V3 Chromium 확장입니다. 이는 기존 `browser_use` 및 `computer_use` 도구를 보완하도록 설계되었습니다.

- `computer_use` / `browser_computer`: 보이는 창, 컴퓨터 사용 스타일 제어
- `browser_companion`: 사용자가 로그인한 브라우저 프로필 내의 DOM 인식 브라우저 제어

이를 통해 Rumi는 모델이 DOM 상태를 검사하고, 연결된 브라우저 중에서 선택하고, 사용자의 라이브 쿠키 및 세션으로 작동할 수 있는 "컴퓨터 사용 + 브라우저 사용" 경로를 제공합니다.

## 파일

- `manifest.json`: 확장 매니페스트
- `background.js`: 브리지 폴링, 브라우저 메타데이터, 탭 작업, 캡처 조정
- `content_script.js`: DOM 스냅샷 및 요소 수준 작업
- `options.html`, `options.css`, `options.js`: 로컬 브리지 구성 UI

## 설치

1. Chrome, Edge, Brave, Vivaldi 등 Chromium 기반 브라우저를 엽니다.
2. 브라우저의 확장 페이지를 열고 개발자 모드를 활성화합니다.
3. "압축해제된 항목 로드"를 선택하고 다음 폴더를 선택합니다.

   `<repo>/rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/rumi_browser_companion`

4. Rumi에서 `action: "bridge.pairing"`과 함께 `browser_companion`을 호출하여 페어링 토큰과 후보 서버 URL을 가져옵니다.
5. 확장 옵션 페이지를 열고 다음을 붙여넣습니다.

   - `http://127.0.0.1:8766` 등 `Server URL`
   - `Pairing Token`

6. `Poll Bridge Now`을 클릭하여 확장 프로그램을 연결할 수 있는지 확인하세요.

## 브릿지 API

확장 프로그램은 다음 로컬 엔드포인트와 통신합니다.

- `POST {serverUrl}/api/tools/browser-companion/bridge/poll`
- `POST {serverUrl}/api/tools/browser-companion/bridge/result`

`poll` 요청 본문:

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

`poll` 응답 본문:

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

`result` 요청 본문:

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

## 지원되는 작업

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

## 안전 참고사항

- 이 확장 프로그램은 사용자의 실제 브라우저 프로필에 있는 페이지를 검사하고 작업할 수 있습니다.
- 귀하가 제어하는 로컬 루미 서버와만 페어링하세요.
- 페어링 토큰을 공유하지 마세요.
- 캡처 및 탭 선택이 브라우저 탭을 포그라운드로 표시할 수 있습니다.
- DOM 작업은 최선의 노력이며 모든 페이지에서 작동하지 않을 수 있습니다.

## 메모

- 확장 프로그램은 사용자의 실제 브라우저 프로필을 사용하므로 인증된 페이지는 사용자의 기존 쿠키 및 세션과 함께 작동합니다.
- DOM 스냅샷 및 요소 작업은 이미 로드된 콘텐츠 스크립트가 있는 탭을 대상으로 할 수 있습니다.
- 표시 탭 캡처는 여전히 브라우저의 활성 표시 탭에 따라 달라지므로 캡처 요청이 대상 탭을 활성화할 수 있습니다.
