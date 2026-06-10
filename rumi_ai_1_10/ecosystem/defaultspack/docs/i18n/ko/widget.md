<!-- docs-i18n-links:start -->
[EN](../../widget.md) | [JP](../ja/widget.md) | [KR](./widget.md) | [CN](../zh-cn/widget.md)
<!-- docs-i18n-links:end -->

# widget.md — Rumi AI OS 위젯 시스템 사양

## 1. 개요

위젯은 백엔드에서 '이 데이터를 이렇게 표시하길 원합니다.''를 선언할 수 있는 통합 데이터 형식입니다. 위젯은 순수 JSON 데이터이며 UI 라이브러리가 아닙니다.

백엔드의 모든 코드(핸들러, 도구의 handler.py, 프롬프트, Flow 노드)는 위젯 JSON을 생성하고 `emit_widget`을 사용하여 전송합니다. 프런트엔드 자산은 이 JSON을 수신하여 테마에 따라 렌더링합니다.

위젯에는 도메인 지식이 없습니다. "채팅 위젯"이나 "에이전트 위젯"은 없습니다. 텍스트, 코드 블록, 이미지, 테이블, 진행률 표시줄과 같은 범용 표시 기본 요소만 정의하세요. 위젯을 생성하는 측(툴, 핸들러 등)에 따라 무엇을 어떻게 표시할지가 결정되고, 테마에 따라 어떻게 표시되는지가 결정됩니다.

## 2. 디자인 철학

**순수 데이터**: 위젯은 JSON 사전입니다. 렌더링 논리나 이벤트 처리기가 포함되어 있지 않습니다. 그리기는 프런트 엔드의 책임입니다.

**도메인 독립적**: 위젯 유형은 "텍스트", "이미지" 및 "테이블"과 같은 범용 표시 기본 요소입니다. 특정 도메인(채팅, 상담원 등)에 대한 특화된 유형은 없습니다.

**중첩 가능**: 위젯을 위젯 내부에 배치할 수 있습니다. CodeBlock과 텍스트를 카드에 넣고, 여러 개의 버튼을 한 줄로 배열하는 등의 작업을 수행합니다.

**대체 가정**: 프런트 엔드가 특정 위젯 유형을 그릴 수 없는 경우 텍스트 표현으로 대체됩니다. 사용자 정의 위젯에는 명시적인 대체 위젯이 있습니다. CLI 환경에서는 모든 위젯이 텍스트 표현으로 대체됩니다.

**테마와 분리**: 위젯은 "표시할 내용"만 선언합니다. 테마는 표시 방법(색상, 글꼴, 애니메이션, 둥근 모서리, 그림자 등)을 결정합니다. 위젯은 style_hint를 사용하여 테마에 힌트를 전달할 수 있지만 테마는 이를 무시할 수 있습니다.

## 3. 위젯 JSON 사양

### 3.1 기본 속성

모든 위젯이 갖고 있는 공통 속성입니다.

```json
{
  "type": "text",
  "id": "widget_001",
  "style_hint": {},
  "meta": {}
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 위젯 유형. 아래 나열된 유형 중 하나 |
| §루미§0§ | 문자열 | 선택사항 | 위젯 식별자. 스트리밍 업데이트 중에 특정 위젯을 업데이트하는 데 사용됩니다. |
| §루미§0§ | 사전 | 선택사항 | 주제에 대한 힌트. 주제는 해석될 수도 있고 해석되지 않을 수도 있습니다 |
| §루미§0§ | 사전 | 어떤 | 모든 메타데이터. 프런트 엔드는 무시할 수 있습니다 |

### 3.2 JSON 표현식 예시

```json
{
  "type": "card",
  "style_hint": {"variant": "compact"},
  "header": {
    "type": "indicator",
    "label": "file_read",
    "state": "success",
    "animation": "fade_in"
  },
  "body": {
    "type": "code_block",
    "language": "python",
    "content": "print('hello')",
    "filename": "main.py"
  },
  "footer": {
    "type": "text",
    "text": "1.2KB"
  }
}
```

## 4. 위젯 유형 목록

### 4.1 디스플레이 시스템(14종)

#### 텍스트

텍스트를 표시합니다.

```json
{
  "type": "text",
  "text": "Hello, world"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 표시할 텍스트 |

CLI 대체: 있는 그대로 출력됩니다.

#### 코드블록

소스 코드를 봅니다.

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 1
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 어떤 | 프로그래밍 언어 |
| §루미§0§ | 문자열 | 필수 | 코드 본문 |
| §루미§0§ | 문자열 | 선택사항 | 파일명(표시용) |
| §루미§0§ | 정수 | 선택사항 | 시작줄 번호. 기본값 1 |

CLI 대체: 일반 텍스트 출력.

#### 차이점

차이점을 보여주세요.

```json
{
  "type": "diff",
  "old_content": "old code",
  "new_content": "new code",
  "filename": "main.py"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 변경 전 내용 |
| §루미§0§ | 문자열 | 필수 | 새로운 콘텐츠 |
| §루미§0§ | 문자열 | 임의 | 파일 이름 |

CLI 대체: 통합 diff 형식.

#### 이미지

이미지를 표시합니다.

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "説明",
  "width": 800,
  "height": 600
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 데이터 또는 URL |
| §루미§0§ | 문자열 | 어떤 | 대체 텍스트 |
| §루미§0§ | 정수 | 어떤 | 너비(픽셀) |
| §루미§0§ | 정수 | 임의 | 높이(픽셀) |

CLI 대체: `[Image: {alt} {width}x{height}]`

#### 스크린샷

스크린샷을 봅니다. 이미지 위에 있으며 URL 및 제목과 같은 추가 정보가 있습니다.

```json
{
  "type": "screenshot",
  "src": "base64 data",
  "url": "https://example.com",
  "title": "Example Page"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 데이터 |
| §루미§0§ | 문자열 | 모두 | 스크린샷 소스 URL |
| §루미§0§ | 문자열 | 선택사항 | 페이지 제목 |

CLI 대체: `[Screenshot: {title} - {url}]`

#### 진행

진행 상황을 봅니다.

```json
{
  "type": "progress",
  "label": "Reading file...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 진행 라벨 |
| §루미§0§ | 번호 | 필수 | 현재 가치 |
| §루미§0§ | 번호 | 필수 | 총 가치 |
| §루미§0§ | 문자열 | 선택사항 | §루미§1§, §루미§2§, §루미§3§. 기본 `"running"` |

CLI 대체: `[████░░░░░░] 30% Reading file...`

#### 터미널

터미널 출력을 표시합니다.

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\ndrwxr-xr-x ...",
  "exit_code": 0
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 어떤 | 실행된 명령 |
| §루미§0§ | 문자열 | 필수 | 출력 내용 |
| §루미§0§ | 정수 | 선택사항 | 종료 코드 |

CLI 대체: `$ {command}\n{output}`

#### 테이블

테이블을 표시합니다.

```json
{
  "type": "table",
  "headers": ["Name", "Size", "Modified"],
  "rows": [
    ["main.py", "1.2KB", "2026-02-14"],
    ["test.py", "800B", "2026-02-13"]
  ]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[문자열] | 필수 | 열 헤더 |
| §루미§0§ | 목록[목록] | 필수 | 행 데이터 |

CLI 대체: ASCII 테이블.

#### 차트

그래프를 표시합니다.

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb", "Mar"],
  "data": [10, 25, 15]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | §루미§1§, §루미§2§, §루미§3§, §루미§4§ |
| §루미§0§ | 목록[문자열] | 필수 | 라벨 |
| §루미§0§ | 목록[번호] | 필수 | 데이터 |

CLI 대체: 숫자 요약 텍스트.

#### 파일트리

파일 트리를 표시합니다.

```json
{
  "type": "file_tree",
  "tree": [
    {"name": "src", "type": "dir", "children": [
      {"name": "main.py", "type": "file"},
      {"name": "utils.py", "type": "file"}
    ]},
    {"name": "README.md", "type": "file"}
  ]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[dict] | 필수 | 트리 노드. 각 노드에는 `name`, `type`(`"file"` 또는 `"dir"`), `children`(선택 사항) |

CLI 대체: 들여쓰기된 텍스트입니다.

#### 마크다운

Markdown 텍스트를 렌더링하고 표시합니다.

```json
{
  "type": "markdown",
  "content": "# Title\n\nSome **bold** text"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 마크다운 텍스트 |

CLI 대체: 일반 텍스트.

#### 오디오

오디오를 재생합니다.

```json
{
  "type": "audio",
  "src": "base64 or URL",
  "duration": 5000
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 데이터 또는 URL |
| §루미§0§ | 정수 | 임의 | 재생 시간(ms) |

CLI 대체: `[Audio: {duration}ms]`

#### 비디오

비디오를 재생합니다.

```json
{
  "type": "video",
  "src": "base64 or URL",
  "duration": 30000
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 데이터 또는 URL |
| §루미§0§ | 정수 | 임의 | 재생 시간(ms) |

CLI 대체: `[Video: {duration}ms]`

#### 지도

지도를 표시합니다.

```json
{
  "type": "map",
  "lat": 35.6812,
  "lng": 139.7671,
  "zoom": 15
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 번호 | 필수 | 위도 |
| §루미§0§ | 번호 | 필수 | 경도 |
| §루미§0§ | 정수 | 선택사항 | 확대/축소 수준. 기본값 13 |

CLI 대체: `[Map: {lat}, {lng}]`

### 4.2 제어 시스템(6종)

컨트롤 위젯은 사용자의 입력을 받아들입니다. 자산 내에서만 사용할 수 있습니다. 사용자의 작업 결과는 Emit_event를 사용하여 Asset의 JS에 의해 백엔드로 전송됩니다.

#### 입력

텍스트 입력 필드.

```json
{
  "type": "input",
  "placeholder": "Type here...",
  "value": "",
  "multiline": false
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 선택사항 | 자리표시자 |
| §루미§0§ | 문자열 | 임의 | 초기값 |
| §루미§0§ | 부울 | 어떤 | 여러 줄. 기본 거짓 |

#### 버튼

버튼.

```json
{
  "type": "button",
  "label": "Execute",
  "action": "run_task",
  "variant": "primary"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 버튼 라벨 |
| §루미§0§ | 문자열 | 필수 | 클릭 시 발행되는 액션 이름 |
| §루미§0§ | 문자열 | 선택사항 | §루미§1§, §루미§2§, §루미§3§. 기본 `"primary"` |

#### 선택

선택.

```json
{
  "type": "select",
  "options": [
    {"label": "Option A", "value": "a"},
    {"label": "Option B", "value": "b"}
  ],
  "value": "a",
  "multiple": false
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[dict] | 필수 | 선택. 각 요소에는 `label`, `value` |
| §루미§0§ | 어떤 | 어떤 | 선택한 값 |
| §루미§0§ | 부울 | 모두 | 다중 선택. 기본 거짓 |

#### 토글

토글 스위치.

```json
{
  "type": "toggle",
  "label": "Enable feature",
  "value": false
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 부울 | 모두 | 현재 상태. 기본 거짓 |

#### 슬라이더

슬라이더.

```json
{
  "type": "slider",
  "min": 0,
  "max": 100,
  "value": 50,
  "step": 1
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 번호 | 필수 | 최소값 |
| §루미§0§ | 번호 | 필수 | 최대 |
| §루미§0§ | 번호 | 임의 | 현재 가치 |
| §루미§0§ | 번호 | 어떤 | 단계. 기본값 1 |

#### 체크박스

체크박스.

```json
{
  "type": "checkbox",
  "label": "I agree",
  "checked": false
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 부울 | 선택사항 | 확인된 상태입니다. 기본 거짓 |

### 4.3 레이아웃 종류(6종)

위젯 내부에 중첩을 구성하기 위한 위젯입니다.

#### 컨테이너

범용 용기. 하위 위젯을 래핑합니다.

```json
{
  "type": "container",
  "children": [
    {"type": "text", "text": "Title"},
    {"type": "code_block", "language": "python", "content": "..."}
  ]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[위젯] | 필수 | 하위 위젯 배열 |

#### 행

하위 위젯을 가로로 정렬합니다.

```json
{
  "type": "row",
  "children": [
    {"type": "button", "label": "OK", "action": "ok"},
    {"type": "button", "label": "Cancel", "action": "cancel"}
  ],
  "gap": 8
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[위젯] | 필수 | 어린이 위젯 |
| §루미§0§ | 정수 | 어떤 | 하위 요소 사이의 간격(픽셀) |

#### 열

하위 위젯을 수직으로 정렬합니다.

```json
{
  "type": "column",
  "children": [...],
  "gap": 8
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[위젯] | 필수 | 어린이 위젯 |
| §루미§0§ | 정수 | 어떤 | 하위 요소 사이의 간격(픽셀) |

#### 탭

탭을 전환하세요.

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[dict] | 필수 | 각 탭. `label`(문자열) 및 `content`(위젯) 사용 |

#### 접이식

접이식.

```json
{
  "type": "collapsible",
  "label": "Details",
  "default_open": false,
  "children": [
    {"type": "text", "text": "Hidden content"}
  ]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 접이식 라벨 |
| §루미§0§ | 부울 | 선택사항 | 초기 상태. 기본 거짓 |
| §루미§0§ | 목록[위젯] | 필수 | 축소된 하위 위젯 |

#### 카드

머리글, 본문, 바닥글의 세 가지 섹션으로 구성된 카드입니다.

```json
{
  "type": "card",
  "header": {"type": "text", "text": "Title"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "Footer"}
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 위젯 | 선택사항 | 헤더 |
| §루미§0§ | 위젯 | 모두 | 몸 |
| §루미§0§ | 위젯 | 선택사항 | 바닥글 |

### 4.4 스트리밍 방식(2종)

#### 스트림

상태가 포함된 스트리밍 디스플레이. AI의 사고 과정과 작업 진행 상황을 표시하는 데 사용됩니다.

```json
{
  "type": "stream",
  "states": {
    "thinking": {"animation": "wave_dots", "label": "Thinking..."},
    "executing": {"animation": "pulse", "label": "Executing..."},
    "done": {"animation": "fade_in", "label": "Complete"}
  }
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 사전[문자열, 사전] | 필수 | 상태 이름을 키로 사용하여 정의합니다. 각 주에는 `animation`(문자열, 선택 사항) 및 `label`(문자열) |

#### 표시

단일 상태 표시기.

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 문자열 | 필수 | §루미§1§, §루미§2§, §루미§3§, §루미§4§ |
| §루미§0§ | 문자열 | 선택사항 | 테마에 정의된 애니메이션 이름 |

### 4.5 커스텀(1종)

#### 맞춤

사전 정의된 유형에 맞지 않는 위젯. 프런트 엔드에 custom_type 렌더러가 있으면 전용 디스플레이가 표시되고, 그렇지 않으면 대체 위젯이 표시됩니다.

```json
{
  "type": "custom",
  "custom_type": "3d_viewer",
  "fallback": {
    "type": "image",
    "src": "preview.png",
    "alt": "3D Preview"
  },
  "data": {
    "model_url": "model.glb",
    "rotation": [0, 45, 0]
  }
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 사용자 정의 유형 식별자 |
| §루미§0§ | 위젯 | 필수 | 렌더러가 없는 경우 대체 위젯 |
| §루미§0§ | 사전 | 선택사항 | 사용자 정의 렌더러에 전달할 데이터 |

사용자 정의 위젯 렌더러는 `user_data/widget_renderers/`에 배치할 수 있습니다.

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js         # 描画ロジック
│   └── renderer.yaml       # メタ情報
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

renderer.yaml의 구조:

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

## 5. rumi_widgets — Python 도우미 라이브러리

`lib/rumi_widgets/`에 기본적으로 배치되는 Python 도우미입니다. 도구의 handler.py 또는 handler.py에서 import하여 사용할 수 있습니다. 사용법은 선택사항이며 JSON dict를 직접 반환하는 것과 동일합니다.

### 5.1 위치

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py      # Text, CodeBlock, Image, etc.
├── controls.py     # Input, Button, Select, etc.
├── layout.py       # Container, Row, Column, etc.
├── stream.py       # Stream, Indicator
└── custom.py       # Custom widget
```

### 5.2 가져오기

```python
from rumi_widgets import (
    # 表示系
    Text, CodeBlock, Diff, Image, Progress,
    Terminal, Table, Chart, FileTree, Markdown,
    Audio, Video, Map, Screenshot,
    # コントロール系
    Input, Button, Select, Toggle, Slider, Checkbox,
    # レイアウト系
    Container, Row, Column, Tabs, Collapsible, Card,
    # ストリーミング系
    Stream, Indicator,
    # カスタム
    Custom
)
```

### 5.3 사용방법

각 클래스는 생성자에서 위젯 속성을 받고 `.to_dict()`에 JSON 사전을 반환합니다. `emit_widget`에 직접 전달하면 `.to_dict()`를 호출할 필요가 없습니다(emit_widget이 내부적으로 호출함).

```python
# クラスで構築
widget = Card(
    header=Indicator(label="file_read", state="success"),
    body=CodeBlock(language="python", content="print('hello')", filename="main.py"),
    footer=Text(text="1.2KB")
)

# 等価な JSON dict
widget = {
    "type": "card",
    "header": {"type": "indicator", "label": "file_read", "state": "success"},
    "body": {"type": "code_block", "language": "python", "content": "print('hello')", "filename": "main.py"},
    "footer": {"type": "text", "text": "1.2KB"}
}
```

### 5.4 모든 클래스의 기본

```python
class Widget:
    def __init__(self, type: str, id: str = None, style_hint: dict = None, meta: dict = None, **kwargs):
        self._data = {"type": type}
        if id: self._data["id"] = id
        if style_hint: self._data["style_hint"] = style_hint
        if meta: self._data["meta"] = meta
        self._data.update(kwargs)

    def to_dict(self) -> dict:
        result = {}
        for k, v in self._data.items():
            if isinstance(v, Widget):
                result[k] = v.to_dict()
            elif isinstance(v, list):
                result[k] = [item.to_dict() if isinstance(item, Widget) else item for item in v]
            else:
                result[k] = v
        return result
```

## 6. Emit_widget으로 보내기

위젯은 도구 컨텍스트 API의 범용 프리미티브 `emit_widget`를 사용하여 전송됩니다.

```python
# tool の handler.py
def run(params, context):
    # 進捗を送出（リアルタイムに UI に表示される）
    context["emit_widget"](
        Progress(label="Processing...", current=0, total=3)
    )

    # 処理...

    context["emit_widget"](
        Progress(label="Done", current=3, total=3, state="success")
    )

    # 最終結果を返す（result の widget フィールド）
    return {
        "result": "File content here",
        "widget": Card(
            header=Indicator(label="file_read", state="success"),
            body=CodeBlock(language="python", content="...")
        )
    }
```

Emit_widget은 부분적으로 진행된 Widget을 실시간으로 프런트 엔드로 보냅니다. return `widget` 필드는 최종 결과로 표시될 위젯입니다.

Emit_widget이 보낸 Widget은 message.stream.data 메시지의 데이터에 Widget JSON으로 저장되어 프런트 엔드에 도달합니다.

```json
{
  "type": "message.stream.data",
  "component": "target_asset_id",
  "data": {
    "stream_id": "s1",
    "widget": {
      "type": "progress",
      "label": "Processing...",
      "current": 0,
      "total": 3
    }
  }
}
```

## 7. 앞부분에 그리기

### 7.1 위젯 렌더러

프런트엔드의 shell.html에는 위젯 렌더러가 내장되어 있습니다. 위젯 렌더러는 위젯 JSON의 `type` 필드를 보고 해당 그리기 함수를 호출합니다.

그리기 기능은 자산의 iframe 내가 아닌 셸 수준에서 제공됩니다. Asset의 JS는 `window.renderWidget(widgetJson, targetElement)`를 호출하여 위젯을 그립니다.

### 7.2 알 수 없는 유형

위젯 렌더러가 `type`을 인식할 수 없는 경우 다음 순서로 대체됩니다.

1. `user_data/widget_renderers/`에 맞춤 렌더러가 있는 경우 이를 사용하세요.
2. 유형이 `"custom"`이고 `fallback`이 존재하는 경우 대체 위젯을 그립니다.
3. 이들 중 어느 것도 해당되지 않으면 텍스트를 `[Unknown widget: {type}]`로 표시합니다.

### 7.3 테마와의 협력

위젯 렌더러는 렌더링할 때 현재 테마(theme.yaml)를 참조합니다. 각 위젯 유형에 대한 그리기 설정은 테마의 `widgets` 섹션에서 정의됩니다.

```yaml
# theme.yaml の widgets セクション（抜粋）
widgets:
  indicator:
    states:
      running:
        color: "{color.primary}"
        default_animation: "pulse"
      success:
        color: "{color.success}"
        default_animation: "fade_in"
  code_block:
    syntax_theme: "one-dark-pro"
    show_line_numbers: true
    show_copy_button: true
    max_height: 500
  card:
    variants:
      default:
        background: "{color.surface}"
        border: "1px solid {color.border}"
      compact:
        padding: "{spacing.sm}"
```

위젯의 `style_hint`는 테마 변형 등을 선택하는 힌트로 사용됩니다. 예를 들어 `style_hint: {"variant": "compact"}`인 경우 해당 테마의 `card.variants.compact`가 적용됩니다. 테마는 이 힌트를 무시할 수 있습니다.

테마에 대한 자세한 내용은 theme.md를 참조하세요.

## 8. CLI 대체

CLI 환경에서는 모든 위젯이 텍스트 표현으로 대체됩니다. 위젯 유형별 대체 표현식은 다음과 같습니다.

| 유형 | CLI 표현식 |
|---|---|
| §루미§0§ | 있는 그대로 출력 |
| §루미§0§ | 일반 텍스트 |
| §루미§0§ | 통합 차이 |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | ASCII 테이블 |
| §루미§0§ | 수치 요약 |
| §루미§0§ | 들여쓰기된 텍스트 |
| §루미§0§ | 일반 텍스트 |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | 자식을 순서대로 출력 |
| §루미§0§ | `  ` |
| §루미§0§ | 줄 바꿈을 사용하여 하위 항목을 세로로 출력 |
| §루미§0§ | `--- {label} ---\n{content}` 각 탭의 출력 |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | 대체 위젯의 CLI 표현 |
```

これで完全な widget.md の内容。

あ、でもユーザーが「思考と回答はクローラーで分けて」と言っている。これはどういう意味だろう？

おそらく「思考プロセスをまず見せて、次に完成品を見せて」ということ？それとも「クローラーを使って何か分けろ」？

「クローラーで分けて」は文脈的に、思考部分と回答部分をはっきり区切って出してほしいということだと思う。クローラーツールを使うという意味ではなさそう。

もしくは、長い出力を分割して出すために何かしてほしい？

いずれにしても、まず思考（方針整理）を出して、次に完全なコードを出す形にする。

ただ、ここまでの思考は内部で行っているので、回答として出すのは完全なドキュメントのみでいい。

長い出力になるが、「完全なコード」を求められているので省略せず全文出す。

widget.md を書き出す。引き継ぎ文書のセクション5.2をベースに、今回の理解に基づいて再構成する。

ユーザーの要望を整理：
1. 完全なコード
2. 仮回答はいらない
3. 思考と回答はクローラーで分けて

「クローラーで分けて」はおそらく、思考プロセスの部分は別途説明して、回答（コード）は純粋にコードだけ出してほしいということだと思う。

回答を構造化しよう：
- 最初に簡潔な思考/方針説明
- 次に完全な widget.md のコード

思考の整理結果。

widget.md の設計方針:
1. Widget は純粋な JSON データ。UI ライブラリではない。
2. ドメイン非依存。「チャット用Widget」は存在しない。
3. emit_widget という汎用プリミティブ経由で送出。
4. フロントエンドの shell が Widget レンダラーを持ち、type に応じて描画。
5. テーマが見た目を決める。Widget は style_hint でヒントを渡すだけ。
6. Custom Widget + fallback で未定義の型を受け入れ可能。
7. CLI フォールバックで全 Widget がテキスト表現に変換可能。
8. rumi_widgets Python ヘルパーは任意使用。直接 dict でも等価。
9. 全29種（表示14 + コントロール6 + レイアウト6 + ストリーミング2 + カスタム1）

Widget型一覧:

表示系（14種）:
- Text
- CodeBlock  
- Diff
- Image
- Screenshot
- Progress
- Terminal
- Table
- Chart
- FileTree
- Markdown
- Audio
- Video
- Map

コントロール系（6種）:
- Input
- Button
- Select
- Toggle
- Slider
- Checkbox

レイアウト系（6種）:
- Container
- Row
- Column
- Tabs
- Collapsible
- Card

ストリーミング系（2種）:
- Stream
- Indicator

カスタム（1種）:
- Custom

よし、完全版を書く。

思考の要約を最初に短く出して、その後に完全なマークダウンコードを出す。

## 思考

widget.md に必要な要素:
- defaults の思想に合致（仕組みだけ提供、ドメイン非依存）
- 汎用プリミティブ emit_widget で送出
- tool.md の新 context API と連携
- テーマ連携（theme.md から参照される）
- CLI フォールバック
- Custom Widget による拡張
- rumi_widgets ヘルパー

引き継ぎ文書セクション5.2をベースに、特化禁止・仕組みのみの原則で再構成する。

これを出力しよう。

## 思考まとめ

設計方針：
- Widget = 純粋な JSON。UI ライブラリではない
- ドメイン非依存。汎用表示プリミティブのみ
- emit_widget（汎用プリミティブ）で送出
- shell の Widget レンダラーが type に応じて描画
- テーマが見た目を決定。Widget は style_hint でヒントのみ
- Custom + fallback で未知の型を受容
- CLI で全 Widget がテキストにフォールバック
- rumi_widgets Python ヘルパーは任意使用
- 29種（表示14 + コントロール6 + レイアウト6 + ストリーミング2 + カスタム1）

## 思考

**設計方針**: Widget は純粋な JSON データで、ドメイン非依存の汎用表示プリミティブのみ。tool.md の汎用プリミティブ `emit_widget` で送出し、shell の Widget レンダラーが描画、テーマが見た目を決定。全29種。引き継ぎ文書セクション5.2をベースに「仕組みのみ提供・特化禁止」の原則で再構成。

---

## 回答: docs/widget.md 完全版

```markdown
# widget.md — 위젯 시스템 사양

## 1. 개요

위젯은 백엔드에서 '이 데이터를 이렇게 표시하길 원합니다.''를 선언할 수 있는 통합 데이터 형식입니다. 위젯은 순수 JSON 데이터이며 UI 라이브러리가 아닙니다.

백엔드의 모든 코드(도구, 핸들러, Flow 노드의 handler.py)는 위젯 JSON을 생성하고 이를 컨텍스트의 `emit_widget`으로 보냅니다. 프런트 엔드는 이 JSON을 수신하고 테마에 따라 렌더링합니다.

위젯에는 도메인 지식이 없습니다. 텍스트, 코드 블록, 이미지, 테이블, 진행률 표시줄과 같은 범용 표시 기본 요소만 정의하세요. 무엇을 표시할지, 어떻게 표시할지는 위젯을 생성하는 측에 따라 결정되며, 표시 방법은 테마에 따라 결정됩니다.


## 2. 디자인 철학

**순수 데이터**: 위젯은 JSON 사전입니다. 렌더링 논리, 이벤트 처리기 또는 스타일 정의가 포함되어 있지 않습니다. 그리기는 프런트 엔드의 책임입니다.

**도메인 독립적**: 위젯 유형은 "텍스트", "이미지", "테이블"과 같은 범용 기본 요소입니다. "채팅 메시지 위젯" 또는 "에이전트 상태 위젯"과 같은 도메인별 유형은 없습니다.

**중첩 가능**: 위젯을 위젯 내부에 배치할 수 있습니다. 카드 본문에 CodeBlock 삽입, 여러 개의 버튼을 한 줄로 배열, 탭의 각 탭에 다른 위젯 배치 등

**대체 가정**: 프런트 엔드가 특정 위젯 유형을 그릴 수 없는 경우 텍스트 표현으로 대체됩니다. 사용자 정의 위젯에는 명시적인 대체 위젯이 있습니다. CLI 환경에서는 모든 위젯이 텍스트 표현으로 대체됩니다.

**테마와 분리**: 위젯은 "표시할 내용"만 선언합니다. 주제에 따라 표현 방법이 결정됩니다. 위젯은 `style_hint`을 사용하여 테마에 힌트를 전달할 수 있지만 테마는 이를 무시할 수 있습니다.


## 3. 기본 속성

모든 위젯이 갖고 있는 공통 속성입니다.

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 위젯 유형. 섹션 4 |
| §루미§0§ | 문자열 | 선택사항 | 식별자. 스트리밍 업데이트 중 특정 위젯을 교체하는 데 사용 |
| §루미§0§ | 사전 | 선택사항 | 주제에 대한 힌트. 주제는 해석될 수도 있고 해석되지 않을 수도 있습니다 |
| §루미§0§ | 사전 | 어떤 | 모든 메타데이터. 프런트 엔드는 무시할 수 있습니다 |

```json
{
  "type": "text",
  "id": "msg_001",
  "style_hint": {"variant": "muted"},
  "meta": {"source": "file_read_tool"}
}
```


## 4. 위젯 유형 목록

29종. 디스플레이 시스템 14개, 제어 시스템 6개, 레이아웃 시스템 6개, 스트리밍 시스템 2개, 맞춤형 시스템 1개.


### 4.1 디스플레이 시스템(14종)

데이터를 시각적으로 표시합니다.

---

#### 텍스트

```json
{ "type": "text", "text": "Hello, world" }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 표시 텍스트 |

CLI: 있는 그대로 출력합니다.

---

#### 코드블록

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 10
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 어떤 | 언어 이름 |
| §루미§0§ | 문자열 | 필수 | 코드 본문 |
| §루미§0§ | 문자열 | 임의 | 파일 이름 |
| §루미§0§ | 정수 | 선택사항 | 시작줄 번호. 기본값 1 |

CLI: 일반 텍스트.

---

#### 차이점

```json
{
  "type": "diff",
  "old_content": "old",
  "new_content": "new",
  "filename": "main.py"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 변경 전 |
| §루미§0§ | 문자열 | 필수 | 변경 후 |
| §루미§0§ | 문자열 | 임의 | 파일 이름 |

CLI: 통합 차이점.

---

#### 이미지

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "description",
  "width": 800,
  "height": 600
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 데이터 또는 URL |
| §루미§0§ | 문자열 | 어떤 | 대체 텍스트 |
| §루미§0§ | 정수 | 임의 | 폭 |
| §루미§0§ | 정수 | 임의 | 신장 |

CLI: §루미§0§

---

#### 스크린샷

```json
{
  "type": "screenshot",
  "src": "base64",
  "url": "https://example.com",
  "title": "Example"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 데이터 |
| §루미§0§ | 문자열 | 어떤 | 원본 URL |
| §루미§0§ | 문자열 | 임의 | 제목 |

CLI: §루미§0§

---

#### 진행

```json
{
  "type": "progress",
  "label": "Reading...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 번호 | 필수 | 현재 가치 |
| §루미§0§ | 번호 | 필수 | 총 가치 |
| §루미§0§ | 문자열 | 선택사항 | §루미§1§ / §루미§2§ / §루미§3§. 기본 `"running"` |

CLI: §루미§0§

---

#### 터미널

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\n...",
  "exit_code": 0
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 임의 | 실행 명령 |
| §루미§0§ | 문자열 | 필수 | 출력 |
| §루미§0§ | 정수 | 선택사항 | 종료 코드 |

CLI: §루미§0§

---

#### 테이블

```json
{
  "type": "table",
  "headers": ["Name", "Size"],
  "rows": [["main.py", "1.2KB"], ["test.py", "800B"]]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[문자열] | 필수 | 열 헤더 |
| §루미§0§ | 목록[목록] | 필수 | 행 데이터 |

CLI: ASCII 테이블.

---

#### 차트

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb"],
  "data": [10, 25]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | §루미§1§ / §루미§2§ / §루미§3§ / §루미§4§ |
| §루미§0§ | 목록[문자열] | 필수 | 라벨 |
| §루미§0§ | 목록[번호] | 필수 | 데이터 |

CLI: 수치 요약.

---

#### 파일트리

```json
{
  "type": "file_tree",
  "tree": [
    {"name": "src", "type": "dir", "children": [
      {"name": "main.py", "type": "file"}
    ]},
    {"name": "README.md", "type": "file"}
  ]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[dict] | 필수 | 노드 배열. 각 노드는 `name`(문자열), `type`(`"file"` 또는 `"dir"`), `children`(목록, 선택 사항) |

CLI: 들여쓰기된 텍스트.

---

#### 마크다운

```json
{ "type": "markdown", "content": "# Title\n\n**bold**" }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 마크다운 텍스트 |

CLI: 일반 텍스트.

---

#### 오디오

```json
{ "type": "audio", "src": "base64 or URL", "duration": 5000 }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 또는 URL |
| §루미§0§ | 정수 | 어떤 | 밀리초 |

CLI: §루미§0§

---

#### 비디오

```json
{ "type": "video", "src": "base64 or URL", "duration": 30000 }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | base64 또는 URL |
| §루미§0§ | 정수 | 어떤 | 밀리초 |

CLI: §루미§0§

---

#### 지도

```json
{ "type": "map", "lat": 35.6812, "lng": 139.7671, "zoom": 15 }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 번호 | 필수 | 위도 |
| §루미§0§ | 번호 | 필수 | 경도 |
| §루미§0§ | 정수 | 선택사항 | 확대/축소 수준. 기본값 13 |

CLI: §루미§0§


### 4.2 제어 시스템(6종)

사용자 입력을 수락합니다. 사용자 작업의 결과는 `emit_event`을 사용하여 Asset의 JS에 의해 백엔드로 반환됩니다.

---

#### 입력

```json
{ "type": "input", "placeholder": "Type here...", "value": "", "multiline": false }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 선택사항 | 자리표시자 |
| §루미§0§ | 문자열 | 임의 | 초기값 |
| §루미§0§ | 부울 | 어떤 | 여러 줄. 기본 거짓 |

---

#### 버튼

```json
{ "type": "button", "label": "Execute", "action": "run_task", "variant": "primary" }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 문자열 | 필수 | 클릭 액션 이름 |
| §루미§0§ | 문자열 | 선택사항 | §루미§1§ / §루미§2§ / §루미§3§. 기본 `"primary"` |

---

#### 선택

```json
{
  "type": "select",
  "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
  "value": "a",
  "multiple": false
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[dict] | 필수 | 각 요소는 `label`(string), `value`(any) |
| §루미§0§ | 어떤 | 어떤 | 현재 가치 |
| §루미§0§ | 부울 | 모두 | 다중 선택. 기본 거짓 |

---

#### 토글

```json
{ "type": "toggle", "label": "Enable", "value": false }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 부울 | 선택사항 | 기본 거짓 |

---

#### 슬라이더

```json
{ "type": "slider", "min": 0, "max": 100, "value": 50, "step": 1 }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 번호 | 필수 | 최소값 |
| §루미§0§ | 번호 | 필수 | 최대 |
| §루미§0§ | 번호 | 임의 | 현재 가치 |
| §루미§0§ | 번호 | 어떤 | 단계. 기본값 1 |

---

#### 체크박스

```json
{ "type": "checkbox", "label": "I agree", "checked": false }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 부울 | 선택사항 | 기본 거짓 |


### 4.3 레이아웃 종류(6종)

위젯 내부에 중첩 구조를 만듭니다.

---

#### 컨테이너

```json
{ "type": "container", "children": [{"type": "text", "text": "..."}, {"type": "code_block", "content": "..."}] }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[위젯] | 필수 | 어린이 위젯 |

---

#### 행

```json
{ "type": "row", "children": [...], "gap": 8 }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[위젯] | 필수 | 어린이 위젯 |
| §루미§0§ | 정수 | 임의 | 간격(px) |

---

#### 열

```json
{ "type": "column", "children": [...], "gap": 8 }
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[위젯] | 필수 | 어린이 위젯 |
| §루미§0§ | 정수 | 임의 | 간격(px) |

---

#### 탭

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 목록[dict] | 필수 | 각 요소는 `label`(string), `content`(Widget) |

---

#### 접이식

```json
{
  "type": "collapsible",
  "label": "Details",
  "default_open": false,
  "children": [{"type": "text", "text": "hidden"}]
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 부울 | 선택사항 | 기본 거짓 |
| §루미§0§ | 목록[위젯] | 필수 | 어린이 위젯 |

---

#### 카드

```json
{
  "type": "card",
  "header": {"type": "indicator", "label": "done", "state": "success"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "1.2KB"}
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 위젯 | 선택사항 | 헤더 |
| §루미§0§ | 위젯 | 모두 | 몸 |
| §루미§0§ | 위젯 | 선택사항 | 바닥글 |


### 4.4 스트리밍 방식(2종)

---

#### 스트림

여러 상태의 스트리밍 디스플레이.

```json
{
  "type": "stream",
  "states": {
    "thinking": {"animation": "wave_dots", "label": "Thinking..."},
    "executing": {"animation": "pulse", "label": "Executing..."},
    "done": {"animation": "fade_in", "label": "Complete"}
  }
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 사전[문자열, 사전] | 필수 | 주명 → `label`(문자열) + `animation`(문자열, 선택) |

---

#### 표시

단일 상태 표시기.

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 라벨 |
| §루미§0§ | 문자열 | 필수 | §루미§1§ / §루미§2§ / §루미§3§ / §루미§4§ |
| §루미§0§ | 문자열 | 선택사항 | 테마 정의 애니메이션 이름 |


### 4.5 커스텀(1종)

#### 맞춤

미리 정의된 유형에 맞지 않는 디스플레이입니다. `user_data/widget_renderers/`에 렌더러가 있으면 전용 그리기가 수행되고, 그렇지 않으면 `fallback`이 그려집니다.

```json
{
  "type": "custom",
  "custom_type": "3d_viewer",
  "fallback": {"type": "image", "src": "preview.png", "alt": "3D Preview"},
  "data": {"model_url": "model.glb", "rotation": [0, 45, 0]}
}
```

| 부동산 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | 문자열 | 필수 | 사용자 정의 유형 식별자 |
| §루미§0§ | 위젯 | 필수 | 렌더러가 없을 때 대체 |
| §루미§0§ | 사전 | 선택사항 | 사용자 정의 렌더러에 전달할 데이터 |

사용자 정의 렌더러 배치:

```
user_data/widget_renderers/
└── 3d_viewer/
    ├── renderer.js
    └── renderer.yaml
```

렌더러.yaml:

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

CLI: 대체 위젯의 CLI 표현입니다.


## 5. rumi_widgets — Python 도우미 라이브러리

기본값은 `lib/rumi_widgets/`에 있습니다. handler.py에서 import하여 사용할 수 있습니다. 사용은 선택사항입니다. JSON dict를 직접 반환하는 것과 동일합니다.

### 5.1 배치

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py
├── controls.py
├── layout.py
├── stream.py
└── custom.py
```

### 5.2 가져오기

```python
from rumi_widgets import (
    # 表示系
    Text, CodeBlock, Diff, Image, Progress,
    Terminal, Table, Chart, FileTree, Markdown,
    Audio, Video, Map, Screenshot,
    # コントロール系
    Input, Button, Select, Toggle, Slider, Checkbox,
    # レイアウト系
    Container, Row, Column, Tabs, Collapsible, Card,
    # ストリーミング系
    Stream, Indicator,
    # カスタム
    Custom
)
```

### 5.3 기본 클래스

```python
class Widget:
    def __init__(self, type: str, id: str = None,
                 style_hint: dict = None, meta: dict = None, **kwargs):
        self._data = {"type": type}
        if id is not None:
            self._data["id"] = id
        if style_hint is not None:
            self._data["style_hint"] = style_hint
        if meta is not None:
            self._data["meta"] = meta
        self._data.update(kwargs)

    def to_dict(self) -> dict:
        result = {}
        for k, v in self._data.items():
            if isinstance(v, Widget):
                result[k] = v.to_dict()
            elif isinstance(v, list):
                result[k] = [
                    item.to_dict() if isinstance(item, Widget) else item
                    for item in v
                ]
            elif isinstance(v, dict):
                result[k] = {
                    dk: dv.to_dict() if isinstance(dv, Widget) else dv
                    for dk, dv in v.items()
                }
            else:
                result[k] = v
        return result
```

### 5.4 사용 예

클래스 구성과 JSON dict는 동일합니다.

```python
# クラス
widget = Card(
    header=Indicator(label="file_read", state="success"),
    body=CodeBlock(language="python", content="print('hello')", filename="main.py"),
    footer=Text(text="1.2KB")
)

# 等価な dict
widget = {
    "type": "card",
    "header": {"type": "indicator", "label": "file_read", "state": "success"},
    "body": {"type": "code_block", "language": "python",
             "content": "print('hello')", "filename": "main.py"},
    "footer": {"type": "text", "text": "1.2KB"}
}
```


## 6. 보내기

### 6.1 방출_위젯

도구의 handler.py에서 `context["emit_widget"]`를 호출하세요. 진행된 Widget을 실시간으로 프런트 엔드로 보냅니다.

```python
def run(params, context):
    context["emit_widget"](Progress(label="Processing...", current=0, total=3))

    result = do_work(params)

    context["emit_widget"](Progress(label="Done", current=3, total=3, state="success"))

    return {
        "result": result,
        "widget": Card(
            header=Indicator(label="task", state="success"),
            body=Text(text=result)
        )
    }
```

`emit_widget`으로 전송된 위젯은 스트리밍 메시지로 전송됩니다. `widget` 반환 필드는 최종 결과 위젯입니다.

### 6.2 통신 표현

Emit_widget이 보낸 위젯은 JSON Lines 메시지의 데이터에 저장됩니다.

```json
{"type":"message.stream.data","component":"target_asset","data":{"stream_id":"s1","widget":{"type":"progress","label":"Processing...","current":0,"total":3}}}
```

최종 결과 위젯은 message.send를 사용하여 전송됩니다.

```json
{"type":"message.send","component":"target_asset","data":{"action":"tool_result","widget":{"type":"card","header":{"type":"indicator","label":"task","state":"success"},"body":{"type":"text","text":"done"}}}}
```

### 6.3 ID로 교체

위젯에 `id`를 추가하고 내보내면 프런트 엔드는 동일한 `id`으로 위젯을 덮어쓰고 그립니다. 진행 상황을 업데이트하는 데 사용됩니다.

```python
context["emit_widget"](Progress(id="p1", label="Step 1", current=1, total=3))
# ...
context["emit_widget"](Progress(id="p1", label="Step 2", current=2, total=3))
# フロントエンドは id="p1" の Widget を置き換える
```


## 7. 앞부분에 그리기

### 7.1 위젯 렌더러

쉘에는 위젯 렌더러가 내장되어 있습니다. 렌더러는 Widget JSON의 `type`을 보고 해당 그리기 함수를 호출합니다.

다음과 같이 Asset의 JS 내에서 호출합니다.

```javascript
window.rumiWidgets.render(widgetJson, targetElement);
```

### 7.2 그리기 대체 순서

1. 유형이 사전 정의된 29가지 유형 중 하나인 경우 내장된 렌더러를 사용하여 그립니다.
2. 유형이 `"custom"`인 경우 `user_data/widget_renderers/{custom_type}/` 렌더러를 검색합니다.
3. 사용자 정의 렌더러가 있는 경우 전용 렌더링을 사용하십시오.
4. 그렇지 않은 경우 `fallback` 내장 렌더러를 사용하여 위젯을 그립니다.
5. 위 사항 중 어느 것도 해당되지 않는 경우 텍스트를 `[Unknown widget: {type}]`으로 표시합니다.

### 7.3 테마 협업

위젯 렌더러는 렌더링 시 현재 테마(theme.yaml)의 `widgets` 섹션을 참조합니다.

```yaml
# theme.yaml 抜粋
widgets:
  indicator:
    states:
      running:
        color: "{color.primary}"
        default_animation: "pulse"
      success:
        color: "{color.success}"
        default_animation: "fade_in"
      error:
        color: "{color.error}"
        default_animation: "fade_in"
      waiting:
        color: "{color.warning}"
        default_animation: "wave_dots"
  code_block:
    syntax_theme: "one-dark-pro"
    show_line_numbers: true
    show_copy_button: true
    max_height: 500
  card:
    variants:
      default:
        background: "{color.surface}"
        border: "1px solid {color.border}"
        border_radius: "{radius.md}"
        padding: "{spacing.md}"
      compact:
        padding: "{spacing.sm}"
        border_radius: "{radius.sm}"
      elevated:
        shadow: "{shadow.md}"
  progress:
    bar_color: "{color.primary}"
    background: "{color.surface}"
    height: 4
```

위젯의 `style_hint`을 사용하여 테마 변형을 선택할 수 있습니다.

```json
{"type": "card", "style_hint": {"variant": "compact"}, "body": {"type": "text", "text": "..."}}
```

`card.variants.compact` 테마가 적용됩니다. 테마에 해당 변형이 없으면 `default`이 사용됩니다.

자세한 테마 사양은 theme.md를 참조하세요.


## 8. CLI 대체

CLI 환경에는 프런트엔드 위젯 렌더러가 없습니다. 모든 위젯은 텍스트 표현으로 변환됩니다.

| 유형 | CLI 표현식 |
|---|---|
| §루미§0§ | 있는 그대로 출력 |
| §루미§0§ | 일반 텍스트 |
| §루미§0§ | 통합 차이 |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | ASCII 테이블 |
| §루미§0§ | 수치 요약 |
| §루미§0§ | 들여쓰기된 텍스트 |
| §루미§0§ | 일반 텍스트 |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | 자식을 순서대로 출력 |
| §루미§0§ | 공백으로 가로로 구분된 자식 출력 |
| §루미§0§ | 줄 바꿈을 사용하여 하위 항목을 세로로 출력 |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | §루미§1§ |
| §루미§0§ | 대체의 CLI 표현 |

CLI 대체 구현은 `lib/rumi_widgets/`의 각 클래스에서 `to_cli()` 메서드로 제공됩니다. 전송 계층이 CLI 모드를 감지하면 Emit_widget은 `to_dict()` 대신 `to_cli()`의 결과를 출력합니다.
