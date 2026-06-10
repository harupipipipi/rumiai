<!-- docs-i18n-links:start -->
[EN](../../../internals/block-signature.md) | [JP](../../ja/internals/block-signature.md) | [KR](./block-signature.md) | [CN](../../zh-cn/internals/block-signature.md)
<!-- docs-i18n-links:end -->

# 블록 서명 사양

기본 팩의 모든 블록은 `blocks/<category>/<name>.py`에 배치되며 통일된 서명을 따릅니다.

---

## `def run(input_data, context)` 규칙

모든 블록은 모듈 수준에서 다음 서명을 사용하여 `run` 함수를 내보냅니다.

```python
def run(input_data: dict, context: dict) -> dict:
```

### input_data의 구조

`input_data`은 클라이언트의 요청 데이터를 저장하는 dict입니다. 전송 계층이 다음을 수행한 후에 전달됩니다.

HTTP의 경우 구문 분석된 JSON 본문인 dict가 그대로 전달됩니다. 경로 매개변수는 전송 계층에 의해 `input_data`에 미리 주입됩니다. 예를 들어 `/api/chat/conversations/{id}`의 경우:

```python
input_data["conversation_id"] = path_params.get("id", "")
```

stdio/UDS의 경우 요청 JSON의 `"data"` 필드 내용이 전달됩니다. 경로 매개변수 주입은 `_ID_INJECT_MAP`에 따라 자동으로 수행됩니다.

`input_data`에 포함된 필드는 각 블록에 따라 다릅니다. 각 블록은 `input_data.get()`을 사용하여 필요한 필드를 얻고, 충분하지 않은 경우 `error()`를 반환합니다.

### 컨텍스트의 모든 필드

#### 직접 호출 시 전송 필드

각 전송에 대해 `_build_context()`에 의해 생성된 기본 필드입니다. 모든 통화에 참석해야 합니다.

| 필드 | 유형 | 설명 |
|---|---|---|
| §루미§0§ | §루미§1§ | 실행 흐름 식별자입니다. 전송 직접 호출하는 경우 `"transport_direct"`(HTTP), `"stdio_direct"`(stdio) 또는 `"uds_direct"`(UDS) |
| §루미§0§ | §루미§1§ | 단계의 식별자입니다. 전송 직접 호출하는 경우 `"http_request"`(HTTP), `"stdio_request"`(stdio) 또는 `"uds_request"`(UDS) |
| §루미§0§ | §루미§1§ | 항상 `"execute"` |
| §루미§0§ | §루미§1§ | ISO 8601 타임스탬프(예: `"2025-01-01T00:00:00Z"`) |
| §루미§0§ | §루미§1§ | 항상 `"defaults"` |
| §루미§0§ | §루미§1§ | 추가 입력. 일반적으로 비어 있는 dict |

#### Flow 엔진/커널을 통해 추가된 필드

핸들러가 Flow 엔진이나 `call_handler`을 통해 호출되면 커널은 다음과 같은 추가 필드를 컨텍스트에 삽입합니다. 이러한 필드는 전송을 직접 호출할 때 존재하지 않습니다(핸들러는 `context.get()`를 사용하여 안전하게 검색해야 합니다).

| 필드 | 유형 | 설명 |
|---|---|---|
| §루미§0§ | §루미§1§ | 다른 핸들러를 호출하는 함수입니다. `call_handler(handler_name: str, input_data: dict) -> dict`의 서명. 커널의 InterfaceRegistry를 통해 핸들러 이름을 확인하고 대상 `run()` |
| §루미§0§ | §루미§1§ | 이벤트를 발생시키는 함수입니다. `emit_event(event_type: str, data: dict) -> None`의 서명. 커널의 EventBus에 이벤트 보내기 |
| §루미§0§ | §루미§1§ | 이벤트를 기다리는 함수입니다. `wait_event(event_type: str, timeout: int, filter: dict) -> dict \| None`의 서명. 지정된 이벤트가 발생할 때까지 차단 |
| §루미§0§ | §루미§1§ | 위젯을 UI로 보내는 함수입니다. `emit_widget(widget_json: dict) -> None`의 서명. `lib/rumi_widgets/`에 정의된 위젯 구조 보내기 |
| §루미§0§ | §루미§1§ | 현재 실행이 취소되었는지 확인하는 함수입니다. `cancel_check() -> bool`의 서명. 장기 실행 루프에서 주기적으로 호출하고 조기 종료에 사용 |
| §루미§0§ | §루미§1§ | 핸들러 구성 정보. `conditions.json` 등에 정의된 핸들러별 설정은 커널 |
| §루미§0§ | §루미§1§ | 세션 정보. `session_id`, `workspace`와 같은 필드를 포함합니다. 세션 범위 상태 관리에 사용 |

#### 컨텍스트 필드 사용 예

```python
def run(input_data, context):
    # transport 直接呼び出し時のベースフィールド（常に存在）
    flow_id = context["flow_id"]
    ts = context["ts"]

    # Flow エンジン経由のフィールド（存在しない場合がある）
    call_handler = context.get("call_handler")
    emit_event = context.get("emit_event")
    emit_widget = context.get("emit_widget")
    cancel_check = context.get("cancel_check")
    session = context.get("session")
    handler_config = context.get("handler_config")

    # call_handler が存在する場合のみ他の handler を呼び出す
    if call_handler is not None:
        result = call_handler("defaults.ai.complete", {
            "model": "openai/gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
        })

    # cancel_check が存在する場合のみキャンセルチェック
    if cancel_check is not None and cancel_check():
        return error("execution cancelled", "CANCELLED")

    return ok({"done": True})
```

---

## 반환 값 — `ok()` / `error()` 형식

모든 블록은 `blocks/_common.py`, `ok()` 또는 `error()`를 사용하여 결과를 반환합니다.

### 성공적인 응답

```python
from blocks._common import ok

return ok({"key": "value"})
# → {"status": "ok", "data": {"key": "value"}}

return ok(None)
# → {"status": "ok", "data": null}
```

### 오류 응답

```python
from blocks._common import error

return error("conversation_id is required", "INVALID_INPUT")
# → {"status": "error", "error": {"code": "INVALID_INPUT", "message": "conversation_id is required"}}

return error("something went wrong")
# → {"status": "error", "error": {"code": "ERROR", "message": "something went wrong"}}
```

### 구현되지 않은 스텁

```python
from blocks._common import not_implemented

return not_implemented("defaults.some.handler")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.some.handler"}
```

### 정적 파일(transport/http.py에만 해당)

HTTP 전송에만 정적 파일을 반환하기 위한 특수 형식이 있습니다.

```python
return {"_static": True, "content_type": "text/html; charset=utf-8", "body": "<html>...</html>"}
```

---

## 가져오기 경로 규칙

모든 블록 파일은 다음 패턴으로 시작 부분에 `sys.path`을 설정합니다.

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
```

이를 통해 팩 루트에서 절대 경로로 가져올 수 있습니다.

```python
from blocks._common import ok, error, gen_id, timestamp
from domain.chat.store import ChatStore
from domain.ai_client.client import AIClient
```

`sys.path.insert(0, ...)`은 파일 시작 부분(다른 가져오기 전)에 작성되어야 합니다.

---

## `_common.py`의 모든 기능

`blocks/_common.py`은 다음과 같은 5가지 기능을 제공합니다:

### §루미§0§

성공 응답을 반환합니다. JSON 직렬화 가능 개체를 `data`에 전달합니다.

```python
ok({"id": "abc"})   # → {"status": "ok", "data": {"id": "abc"}}
ok()                 # → {"status": "ok", "data": null}
```

### §루미§0§

오류 응답을 반환합니다.

```python
error("not found", "NOT_FOUND")  # → {"status": "error", "error": {"code": "NOT_FOUND", "message": "not found"}}
error("fail")                     # → {"status": "error", "error": {"code": "ERROR", "message": "fail"}}
```

### §루미§0§

구현되지 않은 핸들러에 대한 스텁 응답을 반환합니다.

```python
not_implemented("defaults.foo.bar")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.foo.bar"}
```

### §루미§0§

ISO 8601 형식의 UTC 타임스탬프 문자열을 반환합니다.

```python
timestamp()  # → "2025-01-01T00:00:00Z"
```

내부 구현: `time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())`

### §루미§0§

UUID v4 문자열을 반환합니다.

```python
gen_id()  # → "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

내부 구현: `str(uuid.uuid4())`
