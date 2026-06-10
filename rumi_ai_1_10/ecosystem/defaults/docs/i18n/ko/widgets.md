<!-- docs-i18n-links:start -->
[EN](../../widgets.md) | [JP](../ja/widgets.md) | [KR](./widgets.md) | [CN](../zh-cn/widgets.md)
<!-- docs-i18n-links:end -->

# 위젯 가이드

## 1. 위젯 개념

위젯은 백엔드에서 '이 데이터를 이렇게 표시하길 원합니다.''를 선언할 수 있는 통합 JSON 데이터 형식입니다. 위젯은 UI 라이브러리가 아닌 순수 데이터입니다.

백엔드의 모든 코드(핸들러, 도구의 handler.py, 프롬프트, Flow 노드)는 위젯 JSON을 생성하고 `emit_widget`을 사용하여 전송합니다. 프런트엔드의 shell.html에 있는 위젯 렌더러는 이 JSON을 수신하여 테마에 따라 그립니다.

위젯은 도메인 독립적입니다. "채팅 위젯"이나 "에이전트 위젯"은 없습니다. 텍스트, 코드 블록, 이미지, 테이블, 진행률 표시줄과 같은 범용 표시 기본 요소만 정의하세요. 총 29가지 유형(디스플레이 14 + 컨트롤 6 + 레이아웃 6 + 스트리밍 2 + 사용자 정의 1).


## 2. lib/rumi_widgets/의 클래스 목록 및 사용법

`ecosystem/defaults/lib/rumi_widgets/`에 있는 Python 도우미 라이브러리입니다. 사용법은 선택 사항이며 dict를 직접 반환하는 것과 동일합니다.

### display.py(14개 디스플레이 유형)

| 수업 | 사용법 | 주요 매개변수 |
|---|---|---|
| §루미§0§ | 텍스트 표시 | §루미§1§ |
| §루미§0§ | 소스 코드 보기 | §루미§1§, §루미§2§, §루미§3§, §루미§4§ |
| §루미§0§ | 차이 표시 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 이미지 표시 | §루미§1§, §루미§2§, §루미§3§, §루미§4§ |
| §루미§0§ | 스크린샷 표시 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 진행상황 표시 | §루미§1§, §루미§2§, §루미§3§, §루미§4§ |
| §루미§0§ | 단자 출력 표시 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 테이블 표시 | §루미§1§, §루미§2§ |
| §루미§0§ | 그래프 표시 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 파일 트리 표시 | §루미§1§ |
| §루미§0§ | 마크다운 렌더링 | §루미§1§ |
| §루미§0§ | 오디오 재생 | §루미§1§, §루미§2§ |
| §루미§0§ | 비디오 재생 | §루미§1§, §루미§2§ |
| §루미§0§ | 지도 표시 | §루미§1§, §루미§2§, §루미§3§ |

###controls.py(6가지 유형의 컨트롤)

| 수업 | 사용법 | 주요 매개변수 |
|---|---|---|
| §루미§0§ | 텍스트 입력 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 버튼 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 선택 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 토글 스위치 | §루미§1§, §루미§2§ |
| §루미§0§ | 슬라이더 | §루미§1§, §루미§2§, §루미§3§, §루미§4§ |
| §루미§0§ | 체크박스 | §루미§1§, §루미§2§ |

###layout.py(6가지 레이아웃 유형)

| 수업 | 사용법 | 주요 매개변수 |
|---|---|---|
| §루미§0§ | 범용 용기 | §루미§1§ |
| §루미§0§ | 병렬 레이아웃 | §루미§1§, §루미§2§ |
| §루미§0§ | 수직 레이아웃 | §루미§1§, §루미§2§ |
| §루미§0§ | 탭 전환 | `tabs`(각각 `{label, content}`) |
| §루미§0§ | 축소 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 머리글/본문/바닥글이 포함된 카드 | §루미§1§, §루미§2§, §루미§3§ |

### stream.py (스트리밍 유형 2종)

| 수업 | 사용법 | 주요 매개변수 |
|---|---|---|
| §루미§0§ | 상태 기반 스트림 표시 | `states`(딕셔너리) |
| §루미§0§ | 단일 상태 표시기 | §루미§1§, §루미§2§, §루미§3§ |

### custom.py (커스텀 1종)

| 수업 | 사용법 | 주요 매개변수 |
|---|---|---|
| §루미§0§ | 정의되지 않은 위젯 | §루미§1§, §루미§2§, §루미§3§ |


## 3. Python 측에서 JSON을 생성하는 방법

### rumi_widgets 도우미 사용 방법

```python
from rumi_widgets import Card, Indicator, CodeBlock, Text, Row, Button

widget = Card(
    header=Indicator(label="file_read", state="success", animation="fade_in"),
    body=CodeBlock(language="python", content="print('hello')", filename="main.py"),
    footer=Row(children=[
        Button(label="Copy", action="copy"),
        Text(text="1.2KB")
    ])
)

# handler の戻り値で返す
return {"result": "File content", "widget": widget}
```

`emit_widget`(내부적으로 자동 호출됨)으로 전달할 때 `.to_dict()`은 필요하지 않습니다. 또한 `widget` 반환 필드로 전달되면 자동으로 변환됩니다.

### dict로 직접 반환하는 방법

```python
widget = {
    "type": "card",
    "header": {"type": "indicator", "label": "file_read", "state": "success", "animation": "fade_in"},
    "body": {"type": "code_block", "language": "python", "content": "print('hello')", "filename": "main.py"},
    "footer": {
        "type": "row",
        "children": [
            {"type": "button", "label": "Copy", "action": "copy"},
            {"type": "text", "text": "1.2KB"}
        ]
    }
}
return {"result": "File content", "widget": widget}
```

둘 다 완전히 동일한 결과를 생성합니다.


## 4. 앞부분 그리는 방법

위젯 렌더러는 shell.html에 내장되어 있으며 모든 자산에서 공유됩니다.

Asset의 JS에서 위젯을 그리는 방법에는 두 가지가 있습니다.

postMessage 메소드: iframe의 JS는 postMessage를 사용하여 Widget JSON을 상위 창으로 보내고, 상위 위젯 렌더러는 그리기 결과를 반환합니다.

직접 호출 방법: 자산은 `<script>`로 쉘에서 제공하는 `widget-renderer.js`을 가져오고 `renderWidget(widgetJson, targetElement)`를 직접 호출합니다.

```javascript
// Asset の JS 内
// 方法1: postMessage
window.parent.postMessage({
  type: "render_widget",
  widget: widgetJson,
  target: "my-container-id"
}, "*");

// 方法2: 直接呼び出し（widget-renderer.js を読み込み済みの場合）
renderWidget(widgetJson, document.getElementById("my-container"));
```

알 수 없는 위젯 유형은 텍스트로 대체됩니다. `custom` 유형은 `user_data/widget_renderers/`에 커스텀 렌더러가 등록되어 있으면 전용 드로잉을 사용하고, 그렇지 않으면 `fallback` 위젯을 그립니다.


## 5. 사용예

### 예시 1: 파일 읽기 결과를 위젯에 표시하기

```python
def run(params, context):
    content = context["call_handler"]("defaults.coding.file_read", {
        "path": params["path"]
    })
    return {
        "result": content["content"],
        "widget": {
            "type": "card",
            "header": {"type": "indicator", "label": params["path"], "state": "success"},
            "body": {"type": "code_block", "language": "python", "content": content["content"], "filename": params["path"]}
        }
    }
```

### 예시 2: 진행 상황을 실시간으로 표시

```python
def run(params, context):
    files = params["files"]
    for i, f in enumerate(files):
        context["emit_widget"]({
            "type": "progress",
            "label": f"Processing {f}...",
            "current": i,
            "total": len(files),
            "state": "running"
        })
        process(f)

    context["emit_widget"]({
        "type": "progress",
        "label": "Complete",
        "current": len(files),
        "total": len(files),
        "state": "success"
    })
    return {"result": f"Processed {len(files)} files"}
```

### 예시 3: 사용자 확인 버튼

```python
def run(params, context):
    context["emit_widget"]({
        "type": "card",
        "body": {"type": "text", "text": "この操作を実行しますか？"},
        "footer": {
            "type": "row",
            "children": [
                {"type": "button", "label": "実行", "action": "confirm", "variant": "primary"},
                {"type": "button", "label": "キャンセル", "action": "cancel", "variant": "secondary"}
            ]
        }
    })
    response = context["wait_event"]("widget.action", timeout=60)
    if response and response.get("action") == "confirm":
        return {"result": "Executed"}
    return {"result": "Cancelled"}
```

### 예 4: 검색결과 접기

```python
def run(params, context):
    results = context["call_handler"]("defaults.memory.vector_query", {
        "query": params["query"], "top_k": 5
    })
    return {
        "result": "\n---\n".join([r["content"] for r in results["matches"]]),
        "widget": {
            "type": "collapsible",
            "label": f"{len(results['matches'])} results found",
            "default_open": True,
            "children": [
                {"type": "markdown", "content": r["content"]}
                for r in results["matches"]
            ]
        }
    }
```

### 예시 5: 스트리밍 표시기

```python
context["emit_widget"]({
    "type": "indicator",
    "label": "Analyzing code...",
    "state": "running",
    "animation": "pulse"
})
```

animation은 테마의 `animations` 섹션에 정의된 이름을 지정합니다. 테마에서 인식되지 않는 애니메이션 이름은 무시됩니다.
