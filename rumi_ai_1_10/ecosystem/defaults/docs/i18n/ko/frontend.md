<!-- docs-i18n-links:start -->
[EN](../../frontend.md) | [JP](../ja/frontend.md) | [KR](./frontend.md) | [CN](../zh-cn/frontend.md)
<!-- docs-i18n-links:end -->

# frontend.md — Rumi AI OS 프런트 엔드 디자인 문서

## 1. 개요

기본값의 프런트엔드는 Tauri(Rust + WebView)로 구성된 데스크톱 애플리케이션입니다.

프런트 엔드에는 도메인 지식이 없습니다. 채팅이 뭔지도 모르고, 에이전트가 뭔지도 모르고, 파일이 뭔지도 모릅니다. 내가 아는 것은 4가지뿐입니다: ``There is a frame called a slot,'' ``UI blocks called Assets can be placed in the frame,'' ``Widgets can receive drawing instructions,'' and ``메시지는 주고받습니다.''

rumiai 자체가 도메인 지식이 없는 범용 커널인 것과 동일한 구조가 프런트엔드에도 적용됩니다. 모든 도메인 기능은 자산에 의해 제공됩니다. 기본값은 자산을 배치하기 위한 빈 프레임(셸)과 자산을 그리고 통신하는 메커니즘만 제공합니다.

모든 특정 UI(채팅 화면, 에이전트 화면, 코딩 화면 등)는 user_data 측 팩에 의해 자산으로 등록됩니다. 기본값 자체에는 구체적인 UI가 없습니다.


## 2. 아키텍처

```
Tauri App（1プロセス）
├── Rust コア (src-tauri/)
│     ├── Tauri 本体
│     ├── sidecar 管理: rumiai バイナリの起動・終了
│     └── IPC ブリッジ: stdin/stdout ↔ invoke/event/channel
│
├── WebView (src/)
│     ├── シェル: スロットを定義する空の枠
│     ├── Asset ローダー: Asset の動的読み込みと配置
│     ├── Widget レンダラー: Widget JSON を描画する
│     ├── Layout エンジン: layout.json に従い Asset を配置する
│     └── Theme エンジン: theme.yaml に従い見た目を適用する
│
└── rumiai コンパイル済みバイナリ（別プロセス、sidecar）
      └── ecosystem/defaults/
            └── handlers/frontend.py: 通信ブリッジのみ
```

세 개의 레이어가 있습니다.

Rust 레이어는 Tauri의 핵심이며 둘 사이의 통신을 연결합니다. rumiai 프로세스가 포함된 stdin/stdout 및 WebView가 포함된 Tauri IPC(호출/이벤트/채널). Rust 레이어 자체는 메시지 내용을 해석하지 않습니다.

WebView 레이어는 그리기 화면입니다. 셸(빈 프레임 + 슬롯 정의), 자산 로더, 위젯 렌더러, 레이아웃 엔진, 테마 엔진으로 구성됩니다.

rumiai 레이어는 백엔드입니다. 프런트엔드 처리기는 통신을 중계만 하고 도메인 처리는 수행하지 않습니다.


## 3. 권한

프런트엔드에는 12개의 권한만 있습니다. 도메인 권한은 포함되지 않습니다.

| 권한 | 설명 |
|------|------|
| §루미§0§ | 도면 화면에 자산 배치 |
| §루미§0§ | 도면 표면에서 제거 |
| §루미§0§ | 도면 내용 업데이트 |
| §루미§0§ | 백엔드 → 그리기 표면 |
| §루미§0§ | 그리기 표면 → 백엔드 |
| §루미§0§ | 지속적으로 데이터 스트리밍 |
| §루미§0§ | 자산 등록 수락 |
| §루미§0§ | 자산 취소 |
| §루미§0§ | 등록된 내용 |
| §루미§0§ | 현재 레이아웃 정보 가져오기 |
| §루미§0§ | 레이아웃 변경 및 저장 |
| §루미§0§ | 현재 테마 정보 얻기 |


## 4. 자산 모델

Asset은 UI를 프런트엔드로 가져오는 단위입니다. 모든 팩이나 도구는 자산을 등록할 수 있습니다. 프런트 엔드는 자산이 누구인지 상관하지 않습니다.

### 4.1 자산 구성

자산에는 다음이 있습니다.

`asset_id`은 생태계 내에서 고유한 문자열입니다. 명명 규칙은 `{source}.{category}.{name}`입니다. 예를 들어 `defaults.chat.messages` 및 `my_pack.dashboard.main`입니다.

`entry`은 팩 내 HTML 파일(또는 JS 번들)의 상대 경로입니다. 프런트 엔드는 이 파일을 WebView에 로드합니다.

`handler`은 백엔드에서 메시지를 처리하는 Python 파일의 상대 경로입니다. 자산으로 주소가 지정된 메시지는 이 핸들러로 전달됩니다.

`permissions`은 이 자산에 필요한 도메인 권한의 배열입니다. 프런트엔드 권한(`frontend.*`)과는 별도로 자산 자체에 의해 보유됩니다.

`placement`은 이 자산을 어느 슬롯에 배치할지에 대한 힌트입니다. `slot`(슬롯 이름) 및 `priority`(숫자 값, 큰 값이 우선)을 갖습니다.

`category`은 UI의 분류입니다. `"chat"`, `"coding"`, `"settings"` 등 자유 문자열.

`tags`은 검색/필터용 태그 배열입니다.

`requires`은 다른 자산에 대한 의존성입니다. 지정된 자산이 등록되지 않으면 이 자산이 작동하지 않습니다.

`extensions`은 스키마가 없는 확장 필드입니다. 이에 답하는 것은 독자의 몫이다.

### 4.2 자산.yaml

자산 정의 파일. 팩 내의 `assets/` 디렉토리에 넣으세요.

```yaml
asset_id: "my_pack.chat.messages"
name: "Chat Messages"
description: "メッセージ表示エリア"
version: "1.0.0"
source: "my_pack"

entry: "ui/chat/messages.html"
handler: "components/chat_messages.py"

permissions:
  - chat.message.send
  - chat.message.read
  - chat.message.stream
  - ai.completion
  - ai.stream

placement:
  slot: "main"
  priority: 100
  size_hint:
    min_width: 400
    min_height: 300

category: "chat"
tags: ["chat", "messages", "conversation"]

requires: []

on_conflict: "replace"

extensions:
  supports_attachments: true
  supports_voice_input: false
```

### 4.3 자산 등록

`frontend.asset.register`을 통해 자산이 등록되면 프런트 엔드는 다음을 기록합니다.

```json
{
  "asset_id": "my_pack.chat.messages",
  "entry": "ui/chat/messages.html",
  "source": "my_pack",
  "handler": "components/chat_messages.py",
  "permissions": ["chat.message.send", "chat.message.read", "..."],
  "placement": {
    "slot": "main",
    "priority": 100,
    "size_hint": { "min_width": 400, "min_height": 300 }
  },
  "category": "chat",
  "tags": ["chat", "messages"],
  "requires": [],
  "extensions": {}
}
```

프런트 엔드는 이 정보를 사용하여 WebView에 파일을 로드하고layout.json에 따라 정렬합니다. Asset이 무엇을 하는지는 모르겠습니다.

### 4.4 동일한 ID로 덮어쓰기

이미 등록된 자산 ID와 동일한 ID로 `asset.register`이 호출되면 이후 등록이 이전 등록을 대체합니다. 이를 통해 다른 팩이 자산을 대체할 수 있습니다.

### 4.5 도구가 자산을 추가하는 방법

도구 실행 결과의 위젯 출력 외에도 도구에는 자산이 있을 수 있습니다. 도구 디렉토리에 `assets/`를 배치하고 `*.asset.yaml` 및 HTML 파일을 배치합니다. 도구가 설치되면 자산은 "배치되지 않은" 상태로 등록되고 사용자는 레이아웃 편집기를 사용하여 이를 배치합니다.

```
user_data/shared/tools/browser_navigate/
├── tool.json
├── handler.py
└── assets/
    ├── browser_view.asset.yaml
    └── ui/
        └── browser_view.html
```


## 5. 슬롯

슬롯은 자산이 표시되는 프레임입니다. 쉘(shell.html)은 슬롯을 정의합니다.

### 5.1 슬롯 모델

```
┌─────────────────────────────────────────────────┐
│  header                                         │
├──────────┬──────────────────────────┬───────────┤
│ sidebar  │         main             │ sidebar   │
│ .left    │                          │ .right    │
│ [stack]  │  [tabs or split]         │ [stack]   │
│          ├──────────────────────────┤           │
│          │     panel.bottom         │           │
│          │     [tabs]               │           │
├──────────┴──────────────────────────┴───────────┤
│  statusbar                                      │
├─────────────────────────────────────────────────┤
│  floating（モーダル/フローティングウィンドウ）      │
└─────────────────────────────────────────────────┘
```

### 5.2 슬롯 렌더링 모드

| 슬롯 | 모드 | 설명 |
|----------|--------|------|
| §루미§0§ | 싱글 | 수평으로 정렬 |
| §루미§0§ | 스택 | 수직으로 쌓으면 각 자산의 크기를 조정할 수 있습니다 |
| §루미§0§ | 스택 | 수직으로 쌓다 |
| §루미§0§ | 탭 | 탭을 전환하고 분할할 수도 있습니다 |
| §루미§0§ | 탭 | 탭 전환 |
| §루미§0§ | 싱글 | 수평으로 정렬 |
| §루미§0§ | 플로트 | 필요한 경우 오버레이 표시 |

자산은 알 수 없는 슬롯 이름을 지정할 수 있습니다. 쉘이 슬롯을 인식하지 못하면 `floating`으로 대체됩니다.

### 5.3 배치 충돌 해결

여러 자산이 동일한 슬롯에 배치될 때의 규칙입니다. 배치 우선순위가 높은 것(숫자가 더 큰 것)이 우선순위를 가집니다. 우선순위가 같을 경우 나중에 등록한 것이 우선합니다. 사용자가 이를layout.json에 명시적으로 배치하면 우선 순위가 가장 높습니다. 위치를 잃은 자산은 "배치되지 않은" 상태가 됩니다.


## 6. 레이아웃

### 6.1 레이아웃.json

자산의 화면상 배치를 정의합니다. `user_data/layout/`에 저장되었습니다.

```json
{
  "layout_id": "default",
  "name": "Default Layout",
  "slots": {
    "header": {
      "visible": true,
      "height": 48,
      "assets": ["my_pack.ai.model_selector"]
    },
    "sidebar.left": {
      "visible": true,
      "width": 280,
      "assets": [
        { "id": "my_pack.chat.sidebar", "height": "1fr" }
      ]
    },
    "main": {
      "mode": "tabs",
      "active_tab": "my_pack.chat.messages",
      "assets": ["my_pack.chat.messages"],
      "bottom": {
        "asset": "my_pack.chat.input",
        "height": "auto"
      }
    },
    "panel.bottom": {
      "visible": false,
      "height": 250,
      "assets": []
    },
    "statusbar": {
      "visible": true,
      "height": 28,
      "assets": []
    }
  },
  "unplaced": []
}
```

기본값은 이 파일의 형식을 정의합니다. 구체적으로 어떤 자산이 어디에 배치되는지는 user_data 측에 의해 결정됩니다.

### 6.2 사용자가 레이아웃을 편집

일반 모드에서는 자산의 테두리를 드래그하여 크기를 조정합니다. 편집 모드에서는 슬롯 간에 자산을 드래그 및 이동하고, "배치되지 않음" 패널에서 자산을 드래그하여 추가하고, 자산을 닫아 배치되지 않은 상태로 되돌릴 수 있습니다. 여러 레이아웃 사전 설정을 저장하고 전환합니다.

이러한 메커니즘은 셸(shell.html)에 내장되어 있습니다.


## 7. 위젯 렌더링

### 7.1 개요

위젯은 백엔드가 이 데이터를 이와 같이 표시하도록 선언하는 데 사용하는 JSON입니다. 도구의 핸들러, 프롬프트, 에이전트, ai_client 및 모든 백엔드 코드는 위젯을 내보낼 수 있습니다. 프런트엔드 위젯 렌더러는 이 JSON을 수신하여 테마에 따라 그립니다.

위젯은 순수 데이터(JSON)이며 UI 라이브러리가 아닙니다. 렌더링에 대한 책임은 프런트엔드에 있습니다.

### 7.2 위젯 JSON 형식

모든 위젯에는 다음과 같은 기본 속성이 있습니다.

```json
{
  "type": "widget_type",
  "id": "optional_id",
  "style_hint": {},
  "meta": {}
}
```

`type`은 위젯 유형을 나타내는 문자열입니다. `id`은 임의의 식별자입니다. `style_hint`는 테마에 대한 힌트입니다(프론트 엔드에서 해석할 수도 있고 해석하지 않을 수도 있음). `meta`은 선택적 메타데이터입니다(프런트 엔드에서는 무시할 수 있음).

### 7.3 위젯 종류 목록

**디스플레이 종류(14종)**

| 유형 | 설명 | 주요 속성 |
|------|------|---------------|
| §루미§0§ | 텍스트 | 텍스트 |
| §루미§0§ | 코드 | 언어, 내용, 파일 이름, line_start |
| §루미§0§ | 차이 | old_content, new_content, 파일 이름 |
| §루미§0§ | 이미지 | 원본, 대체, 너비, 높이 |
| §루미§0§ | 스크린샷 | 소스, URL, 제목 |
| §루미§0§ | 진행 | 라벨, 현재, 전체, 상태 |
| §루미§0§ | 터미널 출력 | 명령, 출력, 종료_코드 |
| §루미§0§ | 테이블 | 헤더, 행 |
| §루미§0§ | 그래프 | 차트 유형, 데이터, 레이블 |
| §루미§0§ | 파일 트리 | 나무 |
| §루미§0§ | 마크다운 | 내용 |
| §루미§0§ | 오디오 | 소스, 기간 |
| §루미§0§ | 비디오 | 소스, 기간 |
| §루미§0§ | 지도 | 위도, 경도, 확대/축소 |

**제어방식(6종)**

| 유형 | 설명 | 주요 속성 |
|------|------|---------------|
| §루미§0§ | 텍스트 입력 | 자리 표시자, 값, 여러 줄 |
| §루미§0§ | 버튼 | 라벨, 액션, 변형 |
| §루미§0§ | 선택 | 옵션, 값, 다중 |
| §루미§0§ | 토글 | 라벨, 값 |
| §루미§0§ | 슬라이더 | 최소, 최대, 값, 단계 |
| §루미§0§ | 체크박스 | 라벨, 확인됨 |

**레이아웃 종류(6종)**

| 유형 | 설명 | 주요 속성 |
|------|------|---------------|
| §루미§0§ | 일반 컨테이너 | 어린이 |
| §루미§0§ | 나란히 | 어린이, 격차 |
| §루미§0§ | 수직 | 어린이, 격차 |
| §루미§0§ | 탭 전환 | 탭 |
| §루미§0§ | 축소 | 라벨, default_open, 하위 |
| §루미§0§ | 카드 | 머리글, 본문, 바닥글 |

**스트리밍 방식(2종)**

| 유형 | 설명 | 주요 속성 |
|------|------|---------------|
| §루미§0§ | 상태 기반 스트림 | 상태 |
| §루미§0§ | 상태 표시기 | 라벨, 상태, 애니메이션 |

**커스텀(1종)**

| 유형 | 설명 | 주요 속성 |
|------|------|---------------|
| §루미§0§ | 정의되지 않은 위젯 | custom_type, 대체, 데이터 |

### 7.4 위젯 렌더러의 책임

쉘의 내장 위젯 렌더러:

위젯 JSON을 수신하고 `type`에 따라 그리기 기능을 호출합니다. 그리기는 테마(theme.yaml)의 `widgets` 섹션에 정의된 스타일을 따릅니다. 알 수 없음 `type`는 텍스트로 대체됩니다. `custom` 유형은 `custom_type` 렌더러가 등록되어 있으면 전용 그리기를 수행하고, 등록되어 있지 않으면 `fallback` 위젯을 그립니다.

위젯 렌더러는 셸의 일부이며 모든 자산에서 공유됩니다. Asset의 JS는 위젯 JSON을 위젯 렌더러에 전달하여 그리기를 위임할 수 있습니다.

### 7.5 커스텀 위젯 렌더러

사용자 정의 렌더러는 `user_data/widget_renderers/`에 배치할 수 있습니다.

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js
│   └── renderer.yaml
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

renderer.yaml에서 메타데이터(custom_type, version 등)를 정의하고 renderer.js에서 렌더링 로직을 구현합니다. 쉘의 위젯 렌더러가 custom_type을 감지하면 이 JS를 동적으로 로드하고 호출합니다.


## 8. 테마

### 8.1 개요

테마는 모든 레이어의 모양을 제어합니다. 위젯의 색상, 글꼴, 애니메이션 및 그리기 스타일을 정의합니다. `user_data/themes/`에 `.theme.yaml`로 배치됩니다. 테마의 자세한 사양은 `docs/theme.md`에 정의되어 있습니다.

### 8.2 테마 적용하기

셸의 테마 엔진은 `user_data/config.json`에서 `theme_id`를 읽고 해당 `theme.yaml`를 로드합니다. 테마의 `tokens`(색상, 글꼴, 간격 등)을 CSS 변수로 WebView에 삽입합니다. 위젯 렌더러는 이 CSS 변수를 참조하여 그립니다. Asset의 HTML/JS도 이 CSS 변수를 사용할 수 있습니다.

테마 전환은 config.json의 `theme_id`만 변경하면 이루어지며 자산이나 백엔드에는 영향을 주지 않습니다.


## 9. 통신 프로토콜

모든 통신은 세 가지 계층을 거칩니다.

```
WebView ←→ Rust ←→ rumiai
        IPC      stdin/stdout
```

### 9.1 메시지 형식

rumiai와 Rust는 JSON 라인(라인당 하나의 메시지)을 사용하여 통신합니다.

```json
{
  "type": "メッセージタイプ",
  "data": {}
}
```

`type`은 프런트 엔드 권한에 해당하는 작업 이름입니다. `data`은 불투명한 페이로드이며 프런트 엔드와 Rust는 해당 도메인별 콘텐츠를 해석하지 않습니다. 그러나 자산 대상(예: `asset_id`)을 식별하는 데 필요한 필드는 프런트 엔드에서 읽습니다.

### 9.2 메시지 유형

#### 자산.등록

자산 등록. rumiai → 녹 방향.

```json
{
  "type": "asset.register",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "entry": "ui/chat/messages.html",
    "source": "my_pack",
    "handler": "components/chat_messages.py",
    "permissions": ["chat.message.send", "chat.message.read"],
    "placement": {
      "slot": "main",
      "priority": 100
    },
    "category": "chat",
    "tags": ["chat", "messages"],
    "requires": [],
    "extensions": {}
  }
}
```

#### 자산.등록 취소

자산 출시. rumiai → 녹 방향.

```json
{
  "type": "asset.unregister",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### 렌더.마운트

자산 그리기를 시작합니다. rumiai → 녹 방향.

```json
{
  "type": "render.mount",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "slot": "main"
  }
}
```

#### 렌더링.마운트 해제

자산 그리기가 완료되었습니다. rumiai → 녹 방향.

```json
{
  "type": "render.unmount",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### 렌더링.업데이트

도면 내용을 업데이트합니다. rumiai → 녹 방향.

```json
{
  "type": "render.update",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "payload": {
      "unread_count": 3
    }
  }
}
```

`payload`의 내용은 자산에 따라 결정됩니다. 프런트 엔드는 Asset_id를 사용하여 대상을 식별하고 데이터를 있는 그대로 해당 자산에 전달합니다.

#### 메시지.전송

백엔드 → WebView 방향의 단일 메시지. rumiai → 녹 방향.

```json
{
  "type": "message.send",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "payload": {
      "action": "new_message",
      "message_id": "abc123",
      "content": "応答テキスト",
      "widget": {
        "type": "text",
        "text": "応答テキスト"
      }
    }
  }
}
```

`payload`에 `widget` 필드가 있는 경우 위젯 JSON으로 위젯 렌더러에 전달될 수 있습니다. 이는 자산 측의 JS에 의해 결정됩니다. 프런트엔드는 `payload`의 내용을 해석하지 않습니다.

#### 메시지.수신

WebView → 백엔드를 향한 단일 메시지. 녹 → 루미아이 방향.

```json
{
  "type": "message.receive",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "payload": {
      "action": "send",
      "conversation_id": "conv-1",
      "content": "こんにちは"
    }
  }
}
```

#### message.stream.start

스트리밍을 시작하세요. rumiai → 녹 방향.

```json
{
  "type": "message.stream.start",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### message.stream.data

스트리밍 데이터 조각. rumiai → 녹 방향.

```json
{
  "type": "message.stream.data",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1",
    "payload": {
      "chunk": "こん"
    }
  }
}
```

`payload`에는 위젯 JSON도 포함될 수 있습니다. 스트리밍 등의 진행 상황을 표시하는 데 사용됩니다.

```json
{
  "type": "message.stream.data",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1",
    "payload": {
      "widget": {
        "type": "indicator",
        "label": "Thinking...",
        "state": "running",
        "animation": "wave_dots"
      }
    }
  }
}
```

#### message.stream.end

스트리밍 종료. rumiai → 녹 방향.

```json
{
  "type": "message.stream.end",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### 레이아웃.업데이트

레이아웃 변경 알림. 양방향.

```json
{
  "type": "layout.update",
  "data": {
    "layout": { "...layout.json の内容..." }
  }
}
```

#### 레이아웃.저장

레이아웃을 저장합니다. WebView → 루미아이 방향.

```json
{
  "type": "layout.save",
  "data": {
    "layout_id": "my_layout",
    "layout": { "..." }
  }
}
```

#### 테마.변경

테마 전환. 양방향.

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "dark_default"
  }
}
```

#### 이벤트.방송

일반 목적의 이벤트 방송. 양방향. 백엔드의 `emit_event`이 이 메시지가 됩니다.

```json
{
  "type": "event.broadcast",
  "data": {
    "event_type": "ui.popup.show",
    "payload": {
      "popup_id": "consent_1",
      "title": "確認",
      "message": "この操作を実行しますか？",
      "buttons": ["OK", "キャンセル"]
    }
  }
}
```

Asset의 JS는 이 이벤트를 수신하고 팝업을 그린 다음 `event.broadcast`에서 사용자의 응답을 다시 보냅니다. 특정 자산뿐만 아니라 모든 자산이 이벤트를 수신할 수 있습니다. Asset_id를 포함하면 특정 자산으로 주소를 지정할 수 있지만 이는 프런트 엔드의 정렬이 아닌 자산 자체의 필터링에 달려 있습니다.


## 10. Rust 레이어의 책임

Rust 레이어는 다음 작업만 수행합니다. 도메인 지식이 없습니다.

### 10.1 사이드카 관리

Tauri가 시작되면 rumiai 컴파일 바이너리를 사이드카로 시작합니다. `ecosystem/` 디렉터리 경로를 시작 인수로 전달합니다. 사이드카 프로세스를 위한 stdin/stdout 파이프를 보유합니다. 앱이 닫히면 사이드카를 중지합니다.

### 10.2 표준 입력/표준 출력 브리지

rumiai의 stdout에서 JSON 라인을 한 줄씩 읽고 `type` 필드에 따라 WebView로 전송합니다. `render.*`, `message.send`, `message.stream.*`, `event.broadcast`가 Tauri 이벤트/채널에서 WebView로 변환됩니다. `asset.*`는 WebView의 Asset Loader에 이벤트로 통보합니다. `layout.*`은 WebView의 레이아웃 엔진을 알려줍니다. `theme.*`은 WebView의 테마 엔진에 대해 알려줍니다.

WebView에서 `invoke`를 받아 `message.receive`, `layout.save`, `event.broadcast` 형식으로 변환하여 rumiai의 stdin에 씁니다.

### 10.3 메시지의 잘못된 해석

Rust는 `type` 및 `data` 내에서 `asset_id` / `stream_id` / `event_type`만 봅니다. `payload`의 내용은 어떤 방식으로도 해석되어서는 안 됩니다.


## 11. WebView 레이어의 역할

### 11.1 셸

WebView의 진입점은 셸입니다. 쉘은 슬롯(`header`, `sidebar.left`, `main`, `panel.bottom`, `sidebar.right`, `statusbar`, `floating`)을 정의하는 빈 프레임을 그립니다. 슬롯 배치 및 크기는layout.json을 따릅니다.

셸에는 다음이 포함됩니다.

자산 로더: `asset.register` 이벤트를 수신하고 iframe을 사용하여 자산의 HTML 파일을 로드한 후 슬롯에 배치합니다.

위젯 렌더러: 위젯 JSON을 받아 테마에 따라 DOM에 그리는 함수 세트입니다. Asset의 JS는 이 함수를 호출합니다.

레이아웃 엔진: 레이아웃.json을 읽고 슬롯 크기와 자산 배치를 관리합니다. 드래그 앤 드롭 레이아웃 편집 기능을 제공합니다.

테마 엔진: theme.yaml의 토큰을 CSS 변수로 변환하고 WebView에 적용합니다.

이벤트 디스패처: `event.broadcast`을 수신하고 postMessage를 사용하여 모든 자산(iframe)에 전달합니다.

### 11.2 자산 로더

`asset.register`이 수신되면 로더는 자산의 HTML 파일을 로드합니다.

iframe 방법(기본값): iframe을 사용하여 각 자산을 로드합니다. 자산 간 격리도가 높습니다. `postMessage`은 iframe과 상위 창 간의 통신에 사용됩니다.

자산의 HTML에서 상위 창의 위젯 렌더러를 호출할 때 postMessage와 함께 위젯 JSON을 보내면 상위가 렌더링 결과를 반환합니다. 또는 자산 자체가 위젯 렌더러의 JS를 로드하고 자체적으로 그립니다(자산이 `<script>`을 사용하여 쉘에서 제공하는 `widget-renderer.js`를 가져오는 방법).

### 11.3 메시지 발송

Tauri Event를 통해 Rust에서 도착한 `message.send` 및 `message.stream.*`는 `data.asset_id`별로 정렬되어 해당 iframe으로 전송됩니다.

사용자 작업으로 인해 `postMessage`이 iframe 내에서 나오는 경우 이를 `message.receive`로 Rust에 전달합니다.

### 11.4 이벤트 전달

`event.broadcast`은 모든 iframe으로 전달됩니다. 각 자산의 JS는 `event_type`을 확인하고 해당 자산과 관련된 이벤트만 처리합니다.


## 12. 파일 구조

### 12.1 기본 쪽

```
ecosystem/defaults/
├── handlers/
│     └── frontend.py          # 通信ブリッジのみ
├── ui/
│     └── shell.html           # 空の枠 + スロット + Widget レンダラー
│                                + Layout エンジン + Theme エンジン
│                                + Asset ローダー + イベントディスパッチャー
└── lib/
      └── rumi_widgets/        # Widget Python ヘルパー（バックエンド用）
            ├── __init__.py
            ├── display.py
            ├── controls.py
            ├── layout.py
            ├── stream.py
            └── custom.py
```

기본값이 있는 유일한 UI 파일은 shell.html입니다. 채팅, 상담원, 코딩 등에 대한 특정 UI 파일이 없습니다.

### 12.2 타우리 측

```
rumiai-desktop/
├── src/
│     ├── main.tsx             # エントリポイント
│     ├── Shell.tsx            # スロット定義
│     ├── AssetLoader.ts       # Asset の動的読み込み
│     ├── WidgetRenderer.tsx   # Widget JSON → 描画
│     ├── LayoutEngine.ts      # layout.json の管理
│     ├── ThemeEngine.ts       # theme.yaml の適用
│     └── EventDispatcher.ts   # イベント振り分け
├── src-tauri/
│     ├── src/
│     │     ├── lib.rs
│     │     ├── sidecar.rs
│     │     └── bridge.rs
│     ├── binaries/
│     │     └── rumiai-{target}
│     └── capabilities/
│           └── default.json
└── ecosystem/
      └── defaults/
```

### 12.3 user_data 측 (자산 예시)

```
user_data/packs/my_chat_pack/
├── pack.json
├── assets/
│     ├── chat_messages.asset.yaml
│     ├── chat_input.asset.yaml
│     └── chat_sidebar.asset.yaml
├── ui/
│     ├── chat/
│     │     ├── messages.html
│     │     ├── input.html
│     │     └── sidebar.html
│     └── shared/
│           └── styles.css
└── components/
      ├── chat_messages.py
      ├── chat_input.py
      └── chat_sidebar.py
```


## 13. 시작 흐름

```
1. ユーザーが Tauri アプリを起動

2. Rust
   ├── rumiai バイナリを sidecar として起動
   ├── stdin/stdout パイプを確立
   └── WebView を起動（シェルが空のスロットを描画）

3. rumiai
   ├── ecosystem/defaults を読み込み
   └── defaults の frontend handler を実行（通信確立のみ）

4. rumiai がインストール済みパックを走査
   ├── 各パックの assets/ ディレクトリを走査
   ├── *.asset.yaml を読み込み
   └── asset.register メッセージを stdout に送出

5. stdout → Rust → WebView
   ├── Asset ローダーが asset.register を受信
   ├── layout.json を読み込み（なければ各 Asset の placement から自動生成）
   ├── 各 Asset の HTML ファイルを iframe で読み込み
   └── スロットに Asset を配置

6. 画面が完成
   └── ユーザーの操作でレイアウト変更可能
```


## 14. 사용자 작업 흐름

```
1. ユーザーが Asset 内で操作する（例: メッセージを入力して送信）

2. Asset の iframe 内 JS
   └── postMessage({ action: "send", content: "こんにちは" })

3. シェル
   └── postMessage を受信、asset_id を付与
   └── invoke("message_receive", { asset_id: "...", payload: {...} })

4. Rust
   └── stdin に書き込み
       {"type":"message.receive","data":{"asset_id":"...","payload":{...}}}

5. rumiai
   └── frontend handler が受信
   └── asset_id に対応する Asset の handler（components/chat_messages.py）に転送

6. Asset の handler（バックエンド）
   └── ドメイン処理（権限チェック → handler 呼び出し → AI リクエスト等）
   └── 結果を message.send または message.stream で返す

7. stdout → Rust → WebView
   └── Asset の iframe に postMessage で転送
   └── Asset の JS が受け取って UI 更新
   └── Widget JSON があれば Widget レンダラーで描画
```


## 15. 다른 팩이 합류하는 방법

### 15.1 절차

이 팩은 `*.asset.yaml` 및 HTML 파일을 `assets/` 디렉토리에 넣습니다. rumiai의 승인 프로세스(SHA-256 해시 검증 + 사용자 승인)를 통과합니다. 그게 다야. 기본 측면에는 변경 사항이 없습니다.

### 15.2 필수 권한

```yaml
requires:
  # フロントエンドの枠を使う
  - frontend.asset.register
  - frontend.render.mount
  - frontend.render.update
  - frontend.message.send
  - frontend.message.receive

  # 自分のドメイン権限
  - whatever.domain.permission
```

### 15.3 구체적인 예: 날씨 위젯 팩

```
user_data/packs/weather_widget/
├── pack.json
├── assets/
│     └── weather.asset.yaml
├── ui/
│     └── weather.html
└── components/
      └── weather.py
```

```yaml
# weather.asset.yaml
asset_id: "weather.main"
name: "Weather Widget"
entry: "ui/weather.html"
handler: "components/weather.py"
permissions:
  - net.http.request
placement:
  slot: "sidebar.right"
  priority: 50
category: "utility"
tags: ["weather", "widget"]
```

```python
# components/weather.py
def on_message(context, data):
    city = data["payload"].get("city")
    weather = context["call_handler"]("defaults.net.http_get", {
        "url": f"https://api.weather.com/{city}"
    })
    return {
        "type": "message.send",
        "data": {
            "asset_id": "weather.main",
            "payload": {
                "widget": {
                    "type": "card",
                    "header": {"type": "text", "text": city},
                    "body": {"type": "text", "text": weather["temperature"]}
                }
            }
        }
    }
```

### 15.4 구체적인 예: 기존 자산 교체

```yaml
# better_chat.asset.yaml
asset_id: "my_pack.chat.messages"    # 同じ ID で上書き
entry: "ui/better_chat.html"
handler: "components/better_chat.py"
placement:
  slot: "main"
  priority: 200                       # 元より高い priority
```


## 16. 보안

### 16.1 팩 승인

모든 팩은 rumiai의 승인 과정을 거칩니다. SHA-256 해시 확인은 인증 시 코드와 런타임 시 코드가 동일함을 보장합니다.

### 16.2 권한 분리

프런트엔드 권한(`frontend.*`)은 자산 등록, 그리기 및 메시징만 허용합니다. 도메인 작업은 자산 핸들러가 보유한 도메인 권한을 사용하여 수행됩니다.

### 16.3 iframe 격리

각 자산의 UI는 별도의 iframe에서 실행됩니다. 자산 간 직접 DOM 액세스는 불가능합니다. 모든 통신은 `postMessage`을 통해 쉘에 의해 중계됩니다.

### 16.4 데이터 불투명도

Rust 레이어와 프런트 엔드는 메시지의 `payload`를 해석하지 않습니다. 중간 계층이 데이터를 변조할 수 있는 범위를 최소화합니다.

### 16.5 이벤트 필터링

`event.broadcast`은 모든 자산으로 이전됩니다. 이벤트에 기밀 데이터가 포함된 경우 Asset 측 JS에서 `event_type` 및 `asset_id`를 사용하여 필터링을 수행합니다. 프런트엔드 측의 필터링은 신뢰 경계가 아니므로, 이벤트를 발행하기 전에 백엔드 측에서 권한 확인을 수행하십시오.


## 17. 자산 간 통신

자산 간의 직접적인 통신은 정의되지 않습니다. 자산 A가 자산 B에 정보를 보내려는 경우 두 가지 방법이 있습니다.

첫째, 백엔드를 통해. 자산 A는 백엔드에 message.receive를 보내고, 백엔드 핸들러는 이를 처리한 후 message.send를 자산 B에 보냅니다.

둘째, 이벤트를 통해. 자산 A는 event.broadcast에서 이벤트를 내보내고 자산 B는 이벤트를 수신합니다. 이 경우 백엔드(Asset → Rust → rumiai → Emit_event → Rust → All Assets)도 거치게 됩니다.

두 경우 모두 프런트 엔드 내의 자산 간에 직접적인 통신은 없지만 항상 루미아이 백엔드를 통해 이루어집니다.


## 18. 설계 제약 및 주의사항

### 18.1 UI 파일 전달

Asset의 HTML 파일을 WebView로 읽는 방법은 Tauri의 자산 프로토콜(`asset://` 또는 `tauri://`)을 사용하는 것입니다. Tauri의 자산 범위에 팩 디렉터리 경로를 추가해야 합니다.

### 18.2 레이아웃 유연성

슬롯의 유형과 배열은 쉘(shell.html)에 의해 정의됩니다. 셸 자체를 다른 팩으로 교체할 수도 있습니다(`ui/shell.html`를 덮어쓰는 자산을 등록하여).

### 18.3 오프라인 작업

모든 UI 파일은 `ecosystem/` 또는 `user_data/`에 로컬로 위치하므로 인터넷 연결 없이 UI가 그려집니다. 도메인 처리에 네트워크가 필요한지 여부를 결정하는 것은 자산의 책임입니다.

### 18.4 CLI와의 공존

동일한 백엔드(rumiai + 핸들러)는 Tauri 프런트엔드와 CLI 모두에서 액세스할 수 있습니다. CLI의 경우 전송은 stdio이고 위젯 JSON은 텍스트로 대체됩니다. 프런트엔드의 유무는 백엔드의 동작에 영향을 주지 않습니다.
