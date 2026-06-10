<!-- docs-i18n-links:start -->
[EN](../../extending.md) | [JP](../ja/extending.md) | [KR](./extending.md) | [CN](../zh-cn/extending.md)
<!-- docs-i18n-links:end -->

#defaults 팩 확장 가이드

기본 팩에 새로운 기능을 추가하는 절차를 설명합니다.

---

## 새 블록을 추가하는 단계

블록은 기본 팩의 최소 실행 단위입니다. 각 블록은 `blocks/<category>/<name>.py`에 배치되고 `def run(input_data, context)` 기능을 내보냅니다.

### 1. 파일 생성

```
blocks/
  <category>/
    __init__.py      # 空ファイル（既存なら不要）
    <name>.py        # 新しい block
```

### 2. 블록 코드 작성

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp


def run(input_data, context):
    """
    input_data: dict — クライアントからのリクエストデータ
    context: dict — 実行コンテキスト
    """
    # パラメータの検証
    param = input_data.get("param")
    if not param:
        return error("param is required", "INVALID_INPUT")

    # ドメインロジックの呼び出し
    from domain.<module>.<class> import SomeClass
    instance = SomeClass()
    result = instance.some_method(param)

    # 結果を返す
    return ok(result)
```

### 3. 명명 규칙

블록 파일 이름은 뱀 대소문자로 처리기 이름의 마지막 부분에 해당합니다. 예를 들어 `defaults.chat.send` 핸들러는 `blocks/chat/send.py`의 `run()`을 호출합니다.

---

## 새 도메인 모듈을 추가하는 단계

도메인 모듈은 블록으로 불리는 비즈니스 로직 레이어입니다.

### 1. 디렉터리를 생성합니다

```
domain/
  <module_name>/
    __init__.py
    <main_class>.py
```

### 2. 패턴 선택

도메인 모듈은 다음 패턴 중 하나를 따릅니다(자세한 내용은 `docs/internals/domain-patterns.md` 참조).

**싱글톤 패턴** — 상태가 포함된 전역 인스턴스:

```python
class MyService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 初期化処理
```

**스토어 패턴** — 인메모리 데이터 관리:

```python
class MyStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
        return cls._instance
```

### 3. 가져오기 경로

블록에서 도메인 모듈을 사용하는 경우 상대 경로 대신 `sys.path.insert` 완성 팩 루트의 절대 경로를 사용하여 가져옵니다.

```python
from domain.<module>.<file> import ClassName
```

---

## Ecosystem.json을 업데이트하는 방법

새로운 구성 요소를 추가하는 경우 `ecosystem.json`을 업데이트해야 합니다.

### 1. Vocabulary.types에 유형을 추가합니다.

```json
{
  "vocabulary": {
    "types": ["chat", "agent", ..., "new_type"]
  }
}
```

### 2. 구성요소에 항목 추가

```json
{
  "components": {
    "new_module": {
      "type": "new_type",
      "id": "new_module",
      "path": "blocks/new_module",
      "connectivity": {
        "provides": [
          "defaults.new_module.action1",
          "defaults.new_module.action2"
        ]
      }
    }
  }
}
```

### 3. load_order 업데이트

종속성에 따라 순서대로 `load_order` 배열에 항목을 추가합니다.

```json
{
  "load_order": [
    "memory:memory",
    ...,
    "new_type:new_module",
    "frontend:frontend"
  ]
}
```

`frontend`은 항상 마지막에 배치됩니다.

---

## Transport/http.py에 경로를 추가하는 방법

### 1. _setup_routes에 경로를 추가합니다.

`DefaultsHttpServer._setup_routes()` 메서드의 루트 배열에 새 항목을 추가합니다.

```python
("POST", "/api/new_module/action", self._handle_new_action),
```

경로 매개변수가 필요한 경우 `{param}` 형식을 사용하십시오.

```python
("GET", "/api/new_module/{id}/detail", self._handle_new_detail),
```

### 2. 핸들러 메소드 추가

```python
def _handle_new_action(self, request_data, path_params):
    from blocks.new_module.action import run as handler_run
    context = self._build_context()
    return handler_run(request_data, context)

def _handle_new_detail(self, request_data, path_params):
    from blocks.new_module.detail import run as handler_run
    context = self._build_context()
    request_data["item_id"] = path_params.get("id", "")
    return handler_run(request_data, context)
```

### 3. stdio/UDS 전송에도 추가하는 경우

`transport/stdio.py` 및 `transport/uds.py`의 `_ROUTE_MAP` 및 `_ID_INJECT_MAP`에 동일한 경로를 추가합니다.

---

## 테스트 방법

### HTTP를 통한 테스트

```bash
# ヘルスチェック
curl http://127.0.0.1:8766/api/health

# 会話作成
curl -X POST http://127.0.0.1:8766/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"model": "stub/default"}'

# メッセージ送信
curl -X POST http://127.0.0.1:8766/api/chat/conversations/{id}/messages \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "content": "Hello"}}'
```

### stdio를 통한 테스트

```bash
echo '{"method":"GET","path":"/api/health"}' | python -m transport.stdio
```

### 블록 단위 테스트

```python
from blocks.new_module.action import run

context = {
    "flow_id": "test",
    "step_id": "test",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaults",
    "inputs": {},
}

result = run({"param": "value"}, context)
assert result["status"] == "ok"
```
