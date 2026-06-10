<!-- docs-i18n-links:start -->
[EN](../../pack-development-guide.md) | [JP](../ja/pack-development-guide.md) | [KR](./pack-development-guide.md) | [CN](../zh-cn/pack-development-guide.md)
<!-- docs-i18n-links:end -->

# 팩 개발 빠른 시작 가이드

> 자세한 API 참조는 [pack-development.md](./pack-development.md)를 참조하세요.

이 가이드에서는 스캐폴드(템플릿 생성 도구)를 사용하여 첫 번째 Pack을 만들고 Flow에서 호출하고 작동을 확인하는 단계를 설명합니다.

---

## 전제조건

- 파이썬 3.10 이상
- Rumi AI OS 저장소의 복제된 환경
- 저장소 루트에서 작업(`rumi_ai_1_10/` 디렉터리가 존재해야 함)

---

## 1단계: 템플릿을 사용하여 팩 생성

`pack_scaffold` CLI를 사용하여 팩 템플릿을 생성합니다.

```bash
python -m core_runtime.pack_scaffold my_pack --template minimal --output ecosystem/
```

다음 디렉터리 구조가 생성됩니다.

```
ecosystem/my_pack/
├── ecosystem.json
└── __init__.py
```

### 템플릿 유형

| 템플릿 | 내용 |
|-------------|------|
| §루미§0§ | 최소 구성(`ecosystem.json` + `__init__.py`) |
| §루미§0§ | 최소 + `capability_handler.py` |
| §루미§0§ | 최소 + `flows/sample_flow.yaml` |
| §루미§0§ | 모두 포함됨(위의 모든 항목 + `tests/` + `README.md`) |

### CLI 옵션

| 옵션 | 설명 |
|-----------|------|
| §루미§0§, §루미§1§ | 템플릿 유형(기본값: `minimal`) |
| §루미§0§, §루미§1§ | 출력 대상의 상위 디렉터리(기본값: 현재 디렉터리) |
| §루미§0§, §루미§1§ | 기존 디렉터리 덮어쓰기 허용 |

> 처음이라면 `minimal` 템플릿으로 시작하여 필요에 따라 파일을 추가하는 것이 좋습니다.

---

## 2단계: Ecosystem.json 편집

비계에 의해 생성된 `ecosystem.json`를 편집합니다. 스캐폴드 출력에는 `pack_identity`이 포함되어 있지 않으므로 수동으로 추가하세요.

### 스캐폴드에 의해 생성된 Ecosystem.json

```json
{
  "pack_id": "my_pack",
  "version": "0.1.0",
  "description": "my_pack - A Rumi AI OS Pack",
  "capabilities": [],
  "flows": [],
  "connectivity": [],
  "trust": {
    "level": "sandboxed",
    "permissions": []
  }
}
```

### 수정 후 (`pack_identity` 추가)

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:your-username/my_pack",
  "version": "0.1.0",
  "description": "My first Rumi AI OS Pack",
  "capabilities": [],
  "flows": [],
  "connectivity": [],
  "trust": {
    "level": "sandboxed",
    "permissions": []
  }
}
```

### 필수항목

| 필드 | 설명 |
|-----------|------|
| §루미§0§ | 팩 식별자. 디렉터리 이름을 일치시킵니다. `[a-zA-Z0-9_-]{1,64}` |
| §루미§0§ | 배포 소스를 나타내는 식별자(예: `github:author/repo`)입니다. 팩 업데이트 중에 이 값이 변경되면 적용이 거부됩니다 |

> 각 분야에 대한 자세한 사항은 [the ecosystem.json section of pack-development.md](./pack-development.md#생태계json)을 참조하시기 바랍니다.

---

## 3단계: 블록 구현

Pack의 실제 처리는 블록으로 작성됩니다. `backend/blocks/` 디렉터리를 만들고 여기에 Python 파일을 배치합니다.

```
ecosystem/my_pack/
├── ecosystem.json
├── __init__.py
└── backend/
    └── blocks/
        └── hello.py
```

### 최소 블록 구현

```python
# ecosystem/my_pack/backend/blocks/hello.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ（dict）
        context: 実行コンテキスト（dict）
    Returns:
        JSON 互換の dict
    """
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

### run() 함수 서명

`run()` 함수는 다음 세 가지 패턴 중 하나를 허용합니다.

```python
# パターン1: 入力データとコンテキストの両方（推奨）
def run(input_data: dict, context: dict) -> dict | None:
    ...

# パターン2: 入力データのみ
def run(input_data: dict) -> dict | None:
    ...

# パターン3: 引数なし
def run() -> dict | None:
    ...
```

### 중요 참고 사항

**반환 값은 JSON과 호환되어야 합니다**: `dict`, `list`, `str`, `int`, `float`, `bool`, `None` 중 하나를 반환합니다.

**`_` 접두사가 있는 키를 사용하지 마세요**: 반환된 사전에 `_` 접두사(예: `_internal`)로 시작하는 키를 포함하면 커널이 자동으로 이를 제외합니다.

```python
# NG: _ プレフィックスは除外される
def run(input_data, context=None):
    return {"_internal": "removed", "result": "kept"}
    # ctx に格納されるのは {"result": "kept"} のみ

# OK
def run(input_data, context=None):
    return {"result": "kept", "metadata": {"source": "my_pack"}}
```

**입력 데이터 유효성 검사**: `input_data`은 외부 소스에서 제공되므로 유형 및 존재 여부 확인을 수행해야 합니다.

```python
def run(input_data: dict, context: dict) -> dict:
    if not isinstance(input_data, dict):
        return {"error": "input_data must be a dict"}

    name = input_data.get("name")
    if not name or not isinstance(name, str):
        return {"error": "missing or invalid field: name"}

    return {"message": f"Hello, {name}!"}
```

> 자세한 블록 사양은 [the blocks section of pack-development.md](./pack-development.md#블록)을 참조하세요.

---

## 4단계: 유효성 검사

검증 도구를 사용하여 팩 설정이 올바른지 확인하십시오.

```bash
python app.py --validate
```

유효성 검사에서는 다음을 확인합니다.

| 항목 확인 | 설명 |
|-------------|------|
| JSON 구문 분석 | `ecosystem.json`은 유효한 JSON인가요? |
| §루미§0§ 경기 | 디렉터리 이름이 `ecosystem.json`의 `pack_id`과 일치합니까 |
| §루미§0§ 선언 | `connectivity` 필드가 선언되었습니까 |
| `${ctx.*}` 참조 무결성 | `connectivity` |

### 프로그램에서 확인

```python
from core_runtime.pack_validator import validate_packs

report = validate_packs(ecosystem_dir="ecosystem/")
print(f"Pack 数: {report.pack_count}, 有効: {report.valid_count}")

for w in report.warnings:
    print(f"  WARNING: {w}")
for e in report.errors:
    print(f"  ERROR: {e}")
```

---

## 5단계: 테스트

### 수동 테스트

Flow를 직접 실행하여 블록이 작동하는 모습을 볼 수 있습니다. `user_data/shared/flows/`에서 테스트 흐름 파일을 만듭니다.

```yaml
# user_data/shared/flows/test_hello.flow.yaml

flow_id: test_hello
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "Alice"
    output: greeting
```

### Python에서 단위 테스트

블록의 `run()` 함수는 직접 호출하고 테스트할 수 있는 간단한 Python 함수입니다.

```python
# tests/test_hello.py

import sys
sys.path.insert(0, "ecosystem/my_pack/backend")

from blocks.hello import run

def test_hello_basic():
    result = run({"name": "Alice"})
    assert result == {"message": "Hello, Alice!"}

def test_hello_default():
    result = run({})
    assert result == {"message": "Hello, World!"}
```

---

## 6단계: Flow에서 호출

팩 블록은 흐름 정의에서 호출됩니다.

### 흐름 파일 배치

| 경로 | 목적 |
|------|------|
| §루미§0§ | 공유 흐름. 여러 팩에 걸쳐 배선하는 데 사용 |
| §루미§0§ | 팩별 흐름 |

### 흐름 정의 예

```yaml
# user_data/shared/flows/greet.flow.yaml

flow_id: greet
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "${ctx.name}"
    output: greeting
```

### 단계의 주요 필드

| 필드 | 필수 | 설명 |
|-----------|------|------|
| §루미§0§ | ✅ | 단계 ID(흐름 내에서 고유함) |
| §루미§0§ | ✅ | 제휴 단계 |
| §루미§0§ | 선택사항 | 실행 우선순위(오름차순, 기본값 100) |
| §루미§0§ | ✅ | §루미§1§ |
| §루미§0§ | 선택사항 | 소유 팩 ID |
| §루미§0§ | ✅ | 실행 파일의 상대 경로 |
| §루미§0§ | 선택사항 | 입력 데이터(`${ctx.key}`로 가변 확장 가능) |
| §루미§0§ | 선택사항 | 출력 대상 컨텍스트 키 |
| §루미§0§ | 선택사항 | 제한시간 초(기본값 60, 최대 120) |

### 변수 확장

`${ctx.key}`의 맥락에서 값을 참조할 수 있습니다. 중첩된 참조(`${ctx.user.id}`)도 가능합니다. 참조가 존재하지 않는 경우 `null`가 됩니다.

> Flow 정의에 대한 자세한 내용은 [Flow definition section of pack-development.md](./pack-development.md#흐름-정의)을 참조하세요.

---

## 기초 모듈 활용

Rumi AI OS의 핵심 런타임은 Pack 개발에 일반적으로 필요한 기반 모듈을 제공합니다. 아래에서는 각 모듈의 기본 사용법을 소개합니다.

### 구조화된 로그

`core_runtime.logging_utils` 모듈은 JSON 형식의 구조화된 로그 출력을 지원합니다.

```python
from core_runtime.logging_utils import get_structured_logger, CorrelationContext

logger = get_structured_logger("rumi.pack.my_pack")

def run(input_data, context=None):
    logger.info("Processing request", pack_id="my_pack", flow_id=context.get("flow_id"))

    # correlation_id でリクエスト追跡
    with CorrelationContext(correlation_id=context.get("flow_id", "unknown")):
        logger.info("Step started")
        # ... 処理 ...
        logger.info("Step completed")

    return {"status": "ok"}
```

`get_structured_logger()`은 동일한 이름에 대해 동일한 인스턴스를 반환하는 캐시된 팩토리 함수입니다. `bind()` 메서드를 사용하여 고정된 공통 컨텍스트로 로거를 생성할 수 있습니다.

```python
ctx_logger = logger.bind(pack_id="my_pack", flow_id="main_flow")
ctx_logger.info("Step 1")  # pack_id, flow_id が自動付与
ctx_logger.info("Step 2")  # pack_id, flow_id が自動付与
```

출력 형식은 환경 변수 `RUMI_LOG_FORMAT`(`json` 또는 `text`)을 사용하여 제어할 수 있습니다.

> 자세한 내용은 [the structured log settings section of operations.md](./operations.md#구조화된-로그-설정)를 참조하세요.

### 통합 오류

`core_runtime.error_messages` 모듈은 통일된 오류 코딩 체계(`RUMI-{CATEGORY}-{NUMBER}`)를 제공합니다.

```python
from core_runtime.error_messages import format_error, RumiError
from core_runtime.error_messages import VAL_EMPTY_VALUE, PACK_ID_INVALID

def run(input_data, context=None):
    name = input_data.get("name")
    if not name:
        raise format_error(VAL_EMPTY_VALUE, field_name="name")
        # => RumiError: RUMI-VAL-001: name must not be empty

    return {"message": f"Hello, {name}!"}
```

`format_error()`는 `ErrorCode` 상수 템플릿에 매개변수를 포함하고 `RumiError` 인스턴스를 반환합니다. `RumiError`에는 `.code`, `.message`, `.suggestion`, `.details` 속성이 있으며 `.to_dict()`을 사용하여 JSON 직렬화 가능 사전으로 변환될 수 있습니다.

주요 오류 코드 범주: `AUTH`(인증), `NET`(네트워크), `FLOW`(흐름), `PACK`(팩 관리), `CAP`(기능), `VAL`(검증), `SYS`(시스템).

> 자세한 내용은 [the error code reference section of operations.md](./operations.md#오류-코드-참조)를 참조하세요.

### 유형 주석

`core_runtime.types` 모듈은 유형 수준에서 ID 문자열 사용을 지정하기 위한 `NewType`을 제공합니다.

```python
from core_runtime.types import PackId, FlowId, JsonDict, Result

def process_pack(pack_id: PackId, flow_id: FlowId) -> JsonDict:
    return {"pack_id": pack_id, "flow_id": flow_id}

# Result[T] で成功/失敗を表現
def load_data(key: str) -> Result[JsonDict]:
    try:
        data = fetch(key)
        return Result(success=True, value=data)
    except Exception as e:
        return Result(success=False, error=str(e))
```

사용 가능한 유형: `PackId`, `FlowId`, `CapabilityName`, `HandlerKey`, `StoreKey`(NewType), `JsonValue`, `JsonDict`(유형 별칭), `Result[T]`(일반 결과 유형), `Severity`(로그 심각도 열거 유형).

> 자세한 내용은 [the type hints/validation section of pack-development.md](./pack-development.md#힌트검증-입력)을 참조하세요.

### 더 이상 사용되지 않는 API 관리

`core_runtime.deprecation` 모듈의 `deprecated` 데코레이터를 사용하면 더 이상 사용되지 않는 API를 체계적으로 관리할 수 있습니다.

```python
from core_runtime.deprecation import deprecated

@deprecated(since="1.0", removed_in="2.0", alternative="new_handler")
def old_handler(input_data, context=None):
    """この関数は非推奨です。"""
    return new_handler(input_data, context)
```

데코레이터가 주어지면 함수 호출 시 `DeprecationWarning`가 발행되며 자동으로 `DeprecationRegistry`에 등록됩니다. `async def`도 지원됩니다.

경고 동작은 환경 변수 `RUMI_DEPRECATION_LEVEL`(`warn` / `error` / `silent` / `log`)을 사용하여 제어할 수 있습니다.

> 자세한 내용은 [the deprecation warning level control section of operations.md](./operations.md#지원-중단-경고-수준-제어)를 참조하세요.

---

## 다음 단계

이 가이드에서는 최소 팩을 만드는 단계를 설명했습니다. 더 많은 고급 기능을 보려면 아래 pack-development.md 섹션을 참조하세요.

- **기능 핸들러 구현** → [pack-development.md "기능 핸들러 포함"](./pack-development.md#includes-capability-handler)
- **흐름 수정자 생성** → [pack-development.md "Flow Modifier"](./pack-development.md#흐름-수정자)
- **네트워크 액세스 설정** → [pack-development.md "네트워크 액세스"](./pack-development.md#네트워크-접속)
- **팩 간 협력** → [pack-development.md "팩 간 협력 패턴"](./pack-development.md#팩-간-협력-패턴)
- **비밀 사용** → [pack-development.md "Using Secrets (from Pack)"](./pack-development.md#비밀-사용pack에서)
- **스토어 API** → [pack-development.md "스토어 API(기능을 통해)"](./pack-development.md#store-api기능을-통해)
- **원래 엔드포인트 정의** → [pack-development.md "팩별 엔드포인트"](./pack-development.md#팩별-엔드포인트routesjson)
- **스케줄 실행** → [pack-development.md "Flow 정의"](./pack-development.md#흐름-정의)의 스케줄 실행 섹션
- **오류 처리** → [pack-development.md "오류 처리 모범 사례"](./pack-development.md#오류-처리-모범-사례)
