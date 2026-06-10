<!-- docs-i18n-links:start -->
[EN](../../pack-development.md) | [JP](../ja/pack-development.md) | [KR](./pack-development.md) | [CN](../zh-cn/pack-development.md)
<!-- docs-i18n-links:end -->

> **빠른 시작 가이드**: 팩 개발을 시작하려면 [팩 개발 빠른 시작 가이드](./pack-development-guide.md)를 참조하세요.
# Rumi AI OS — 팩 개발 가이드

Pack 개발자를 위한 가이드입니다. 전체 설계는 [architecture.md](./architecture.md)를, 작동 지침은 [operations.md](./operations.md)을 참조하세요.

---

## 목차

1. [개발 흐름](#개발-흐름)
2. [최소 구성](#minimum-configuration)
3. §루미§0§
4. [블록](#블록)
5. §루미§0§
6. [흐름 정의](#흐름-정의)
7. [흐름 → HTTP 응답 매핑](#flow--http-response-mapping)
8. [흐름 수정자](#흐름-수정자)
9. [네트워크 접속](#네트워크-접속)
10. [context\["http\_request"\] 상세 사양](#contexthttp_request-상세 사양)
11. [비밀 사용(팩에서)](#비밀-사용pack에서)
12. [기능 사용](#기능-사용)
13. [스토어 API(기능을 통해)](#store-api기능을-통해)
14. [팩 간 협력 패턴](#팩-간-협력-패턴)
15. §루미§0§
16. [pip 종속성(requirements.lock)](#pip-종속성requirementslock)
17. §루미§0§
18. [기능 처리기 포함](#includes-capability-handler)
19. §루미§0§
20. [구성요소(고급)](#구성요소고급)
21. [팩별 엔드포인트(routes.json)](#팩별-엔드포인트routesjson)
22. [HTTP 상태 코드 제어](#http-상태-코드-제어)
23. [오류 처리 모범 사례](#오류-처리-모범-사례)
24. [흐름 수정자 권장 패턴](#flow-modifier-권장-패턴)
25. [핸들러 API 분류](#핸들러-api-분류)
26. [출력 키 명명 규칙(세부 사항)](#출력-키-명명-규칙세부정보)
27. [참고](#메모)
28. [API 참조](#api-참조)
29. [튜토리얼: 간단한 팩 만들기](#튜토리얼-간단한-팩-만들기)

---

## 개발 흐름

### 0단계: 템플릿을 사용하여 템플릿 생성

```bash
python -m core_runtime.pack_scaffold my-pack --template minimal --output-dir ecosystem/
```

템플릿 유형:
- `minimal`: 최소 구성(ecosystem.json + run.py)
- `capability`: 기능 처리기 포함
- `flow`: 흐름 정의 포함
- `full`: 모두 포함됨

1. **팩 만들기** — `ecosystem/<pack_id>/backend/`에 파일 배치
2. **ecosystem.json 작성** — 팩 메타데이터(`pack_id`, `pack_identity` 필요)
3. **쓰기 블록/** — `python_file_call`에서 호출되는 코드
4. **쓰기 흐름** — 팩 및 연결 블록의 `user_data/shared/flows/` 또는 `flows/`에 배치합니다.
5. **승인 받기** — 사용자가 팩을 승인합니다.
6. **실행** — 승인 후 흐름 실행 시 블록이 호출됩니다.

---

## 최소 구성

```
ecosystem/my_pack/
└── backend/
    ├── ecosystem.json
    └── blocks/
        └── hello.py
```

> **경로 정보**: `ecosystem/<pack_id>/`가 권장 경로입니다. `ecosystem/packs/<pack_id>/`도 호환 경로로 지원되지만, 둘 다 동일한 `pack_id`가 존재할 경우 `ecosystem/<pack_id>/`이 우선 적용됩니다.

---

## 생태계.json

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "version": "1.0.0",
  "description": "My first pack",
  "pack_identity_vocabulary": ["my_pack"]
}
```

| 필드 | 필수 | 설명 |
|-----------|------|------|
| §루미§0§ | ✅ | 팩 식별자. 디렉터리 이름 일치 |
| §루미§0§ | ✅ | 배포자 식별자(예: `github:author/repo`). 팩 업데이트 중에 이 값이 변경되면 적용이 거부됩니다 |
| §루미§0§ | 선택사항 | 의미적 버전 관리 |
| §루미§0§ | 선택사항 | 설명 |
| §루미§0§ | 선택사항 | Pack에서 사용하는 어휘 목록입니다. vocab.txt와의 협업에 사용 |
| §루미§0§ | 선택사항 | 필수 비밀 키 목록(예: `["OPENAI_API_KEY"]`). 이용자에게 정보를 제공하기 위해 |
| §루미§0§ | 선택사항 | 네트워크 요구 사항(예: `{"allowed_domains": ["api.example.com"], "allowed_ports": [443]}`). 이용자에게 정보를 제공하기 위해 |
| §루미§0§ | 선택사항 | 호스트 실행이 필요합니다(`true` / `false`). `true`의 경우 컨테이너 격리 대신 호스트 프로세스로 실행 |

### 연결성(팩 간 종속성 선언)

`ecosystem.json`에 `connectivity` 필드를 추가하여 팩 간의 종속성을 선언할 수 있습니다.

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:author/my_pack",
  "connectivity": {
    "provides": ["ai.client"],
    "requires": ["tool.registry"]
  }
}
```

| 필드 | 설명 |
|-----------|------|
| §루미§0§ | 이 팩에서 제공하는 서비스 이름 목록 |
| §루미§0§ | 이 팩에 필요한 서비스 이름 목록 |

연결 `requires` / `provides`은 시작 시 팩 로드 순서(load_order)를 자동으로 해결하는 데 사용됩니다. `requires`에 명시된 서비스를 `provides`로 먼저 로드하는 팩입니다.

수동 사양(`ecosystem.json`의 `load_order` 필드)이 있는 경우 해당 사양이 우선 적용됩니다. 자동 해결은 수동 지정이 없는 경우에만 적용됩니다.

현재 연결의 유일한 런타임 효과는 자동 load_order 확인입니다. 앞으로는 확장될 수도 있습니다.

#### 연결 패턴 예

| 제공 | 의미 | 일반 팩 |
|----------|------|--------------|
| §루미§0§ | AI API 클라이언트 | OpenAI / Anthropic 클라이언트 |
| §루미§0§ | 도구 등록 | 도구 관리자 |
| §루미§0§ | 메모리 저장소 | 메모리 관리 |
| §루미§0§ | 채팅 UI | 프론트엔드 |

제공/요구 값은 점으로 구분된 자유 문자열입니다. OS는 값의 의미를 해석하지 않고 load_order의 자동 해결에만 사용합니다. 팩 개발자들끼리 이름을 맞춰주세요.

---

## 블록

`python_file_call`에 의해 호출되는 Python 파일입니다.

### 기본 형태

```python
# ecosystem/my_pack/backend/blocks/hello.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ（dict）
        context: 実行コンテキスト（dict）
            - flow_id: 実行中の Flow ID
            - step_id: 実行中のステップ ID
            - phase: 実行中のフェーズ名
            - ts: タイムスタンプ
            - owner_pack: 所有 Pack ID
            - inputs: 入力データ
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> dict
            - capability_socket: Capability UDS ソケットパス（存在する場合）

    Returns:
        JSON 互換の dict
    """
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

`run` 함수는 `input_data`의 단일 인수 버전만 허용합니다.

### 반환값

JSON 호환 사전을 반환하세요. 반환된 값은 흐름의 `output` 필드에 지정된 컨텍스트 키에 그대로 저장됩니다. 커널 내부의 래퍼(예: `_kernel_step_status`)는 자동으로 제거되고 블록에서 반환된 값은 `ctx[output_key]`로 직접 이동됩니다.

### 출력 키 명명 규칙

흐름 단계의 `output`에 저장된 값의 키 이름에는 다음 규칙이 적용됩니다.

`_` 접두사로 시작하는 키는 커널 내부 키로 예약되어 있습니다. `python_file_call`의 `run()`에 의해 반환된 dict에 `_` 접두사가 붙은 키가 포함되어 있는 경우(예: `_kernel_step_status`, `_debug`) Flow의 `output` 컨텍스트에 저장될 때 자동으로 제외됩니다.

Pack 블록에서 반환된 출력 키에 `_` 접두사를 사용하지 마세요. 이로 인해 본의 아니게 제외될 수 있습니다.

```python
# NG: _ プレフィックスは除外される
def run(input_data, context=None):
    return {"_internal": "removed", "result": "kept"}
    # ctx に格納されるのは {"result": "kept"} のみ

# OK: プレフィックスなし
def run(input_data, context=None):
    return {"result": "kept", "metadata": {"source": "my_pack"}}
```

---

## 힌트/검증 입력

### run() 함수 서명

`python_file_call`에 의해 호출되는 `run()` 함수는 다음 세 가지 패턴 중 하나를 허용합니다. 실행 엔진은 `inspect.signature`의 인수 수를 자동 감지합니다.

```python
# パターン1: 入力データとコンテキストの両方を受け取る（推奨）
def run(input_data: dict, context: dict) -> dict | None:
    ...

# パターン2: 入力データのみ受け取る
def run(input_data: dict) -> dict | None:
    ...

# パターン3: 引数なし
def run() -> dict | None:
    ...
```

### input_data에 대한 유형 안전성

`input_data`은 흐름 정의의 `input` 필드에 대한 JSON 직렬화/역직렬화 값입니다. 따라서 포함된 유형은 다음 JSON 파생 유형으로 제한됩니다.

| JSON 유형 | 파이썬 유형 |
|---------|----------|
| 개체 | §루미§0§ |
| 배열 | §루미§0§ |
| 문자열 | §루미§0§ |
| 숫자(정수) | §루미§0§ |
| 숫자(10진수) | §루미§0§ |
| 부울 | §루미§0§ |
| null | §루미§0§ |

`input_data` 자체는 일반적으로 `dict`이지만, 흐름 정의에서 직접 스칼라 값이나 목록을 지정하면 해당 유형이 됩니다.

### 컨텍스트 유형

`context`는 `dict[str, Any]`입니다. 주요 키는 다음과 같습니다:

| 열쇠 | 유형 | 설명 |
|------|----|------|
| §루미§0§ | §루미§1§ | 실행 중인 흐름 ID |
| §루미§0§ | §루미§1§ | 실행 단계 ID |
| §루미§0§ | §루미§1§ | 실행 단계 이름 |
| §루미§0§ | §루미§1§ | 실행 시작 타임스탬프(ISO 8601 UTC) |
| §루미§0§ | §루미§1§ | 소유 팩 ID |
| §루미§0§ | §루미§1§ | input_data와 동일 |
| §루미§0§ | §루미§1§ | HTTP 요청 기능([context\["http\_request"\] 상세 사양](#contexthttp_request-상세 사양) 참조) |
| §루미§0§ | §루미§1§ | 네트워크 접속 확인 기능 |
| §루미§0§ | §루미§1§ | 기능 UDS 소켓 경로 |

### 반환 유형

`run()`의 반환 값은 JSON 직렬화 가능 값(`dict`, `list`, `str`, `int`, `float`, `bool`, `None`)이어야 합니다. `None`을 반환하면 Flow 출력은 `null`로 처리됩니다. 반환 값이 `dict`인 경우 해당 내용은 흐름의 `output` 변수에 저장됩니다.

### 유효성 검사 모범 사례

`input_data`의 내용은 외부 소스(흐름 정의 및 사용자 입력)에서 파생되므로 반드시 유효성을 검사하세요.

```python
def run(input_data: dict, context: dict) -> dict:
    # 1. 型チェック（早期リターン）
    if not isinstance(input_data, dict):
        return {"error": "input_data must be a dict"}

    # 2. 必須フィールドの存在チェック
    url = input_data.get("url")
    if not url:
        return {"error": "missing required field: url"}

    # 3. 型の厳密チェック
    if not isinstance(url, str):
        return {"error": "field 'url' must be a string"}

    timeout = input_data.get("timeout", 30)
    if not isinstance(timeout, (int, float)):
        return {"error": "field 'timeout' must be a number"}

    # 4. 値の範囲チェック
    if timeout <= 0 or timeout > 120:
        return {"error": "field 'timeout' must be between 0 and 120"}

    # 5. 本処理
    result = context["http_request"](
        method="GET",
        url=url,
        timeout_seconds=timeout,
    )
    return {"result": result}
```

**권장사항:**

- 예외를 발생시키는 대신 `{"error": "..."}`을 반환하고 정상적으로 종료합니다.
- 기능 시작 시 모든 필수 필드를 확인하세요.
- `isinstance()`으로 유형을 엄격하게 확인하세요.
- 숫자 범위 및 목록 길이에 대한 제한 설정

---

## 흐름 정의

### 배치 경로

| 경로 | 목적 |
|------|------|
| §루미§0§ | 공유 흐름. 여러 팩에 걸친 배선에 적합 |
| §루미§0§ | 팩별 흐름 |

### 예

```yaml
# user_data/shared/flows/hello.flow.yaml

flow_id: hello
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

### 단계 작성 방법

#### python_file_call

```yaml
- id: generate_response
  phase: generate
  priority: 50
  type: python_file_call
  owner_pack: ai_client
  file: blocks/generate.py
  input:
    user_input: "${ctx.user_input}"
  output: ai_output
  timeout_seconds: 60
```

| 필드 | 필수 | 설명 |
|-----------|------|------|
| §루미§0§ | ✅ | 단계 ID(흐름 내에서 고유함) |
| §루미§0§ | ✅ | 제휴 단계 |
| §루미§0§ | 선택사항 | 실행 우선순위(오름차순, 기본값 100) |
| §루미§0§ | ✅ | §루미§1§ |
| §루미§0§ | 선택사항 | 보유 팩(경로로 유추할 경우 생략 가능) |
| §루미§0§ | ✅ | 실행 파일의 상대 경로 |
| §루미§0§ | 모두 | 입력 데이터(변수 확장 가능) |
| §루미§0§ | 선택사항 | 출력 대상 컨텍스트 키 |
| §루미§0§ | 선택사항 | 시간 초과 초(기본값 60) |

#### 핸들러

```yaml
- id: load_context
  phase: prepare
  priority: 10
  type: handler
  input:
    handler: "kernel:ctx.get"
    args:
      key: "context"
  output: context
```

`handler` 유형은 `input.handler`(`kernel:*`)에 지정된 커널 핸들러 또는 InterfaceRegistry 등록 핸들러를 직접 호출합니다. `input.args`이 핸들러에 인수로 전달됩니다.

#### 세트

```yaml
- id: set_default
  phase: prepare
  priority: 5
  type: set
  input:
    key: "model"
    value: "gpt-4"
```

> **참고**: `set` 유형은 InterfaceRegistry에 등록된 `flow.construct.set` 핸들러에 의해 처리됩니다. 플로우 로더는 `set`를 표준 단계 유형으로 해석하지만 실행은 구성을 통해 이루어집니다. `set` 구문이 등록되지 않은 경우 해당 단계를 건너뜁니다.

#### 흐름(하위 흐름 호출)

```yaml
- id: run_sub_pipeline
  phase: main
  priority: 50
  type: flow
  flow: sub_flow_id
  args:
    param1: "${ctx.value}"
  output: sub_result
```

`flow` 유형은 다른 Flow를 하위 Flow로 호출합니다. 재귀 호출(순환 참조)이 자동으로 감지되어 오류가 발생합니다. 하위 Flow의 컨텍스트는 상위 Flow에서 Deep Copy되며 `args`에 지정된 값이 추가됩니다.

#### 함수(능력 함수 호출)

```yaml
- id: read_store
  phase: main
  priority: 50
  type: function
  function: store.get
  input:
    store_id: "my_store"
    key: "${ctx.key}"
  output: store_result
```

`function` 타입은 `capability_executor`을 통해 FunctionRegistry에 등록된 기능을 실행합니다. `function` 필드에 `permission_id`(예: `store.get`)를 지정합니다. 실행을 위해서는 해당 기능 부여가 필요합니다.

| 필드 | 필수 | 설명 |
|-----------|------|------|
| §루미§0§ | ✅ | §루미§1§ |
| §루미§0§ | ✅ | 실행할 함수의Permission_id (예: `store.get`, `docker.run`) |
| §루미§0§ | 모두 | 함수에 대한 인수(변수 확장 가능) |
| §루미§0§ | 선택사항 | 출력 대상 컨텍스트 키 |
| §루미§0§ | 선택사항 | `true`의 경우 어휘는 해결하기 전에 `function`의 값을 정규화합니다 |

### 변수 확장

`${ctx.key}`의 맥락에서 값을 참조할 수 있습니다. 중첩된 참조(`${ctx.user.id}`)도 가능합니다. 참조가 존재하지 않는 경우 `null`가 됩니다.

### 실행 예약

Flow에 `schedule` 필드를 추가하면 정규 실행이 가능합니다.

#### cron 표현식(5개 필드: 분, 시, 일, 월, 요일)

```yaml
flow_id: daily_cleanup
schedule:
  cron: "0 0 * * *"

phases:
  - main
steps:
  # ...
```

#### 간격(초 지정, 최소 10초)

```yaml
flow_id: health_check
schedule:
  interval: 30

phases:
  - main
steps:
  # ...
```

cron 표현식은 `*`, `*/N`, 숫자, 쉼표로 구분, 범위(`N-M`) 및 범위+단계(`N-M/S`)를 지원합니다. 스케줄러는 10초마다 틱 단위로 평가되므로 cron의 정밀도는 분 단위입니다. 동일한 Flow의 중복 실행을 자동으로 방지합니다.

### 흐름 제어 프로토콜

블록의 반환 값에 `__flow_control` 키를 반환하여 흐름 실행을 제어할 수 있습니다.

#### 흐름 중단

```python
def run(input_data, context=None):
    if not input_data.get("valid"):
        return {"__flow_control": "abort", "reason": "Invalid input"}
    return {"result": "ok"}
```

`{"__flow_control": "abort", "reason": "..."}`을 반환하면 추가 단계를 실행하지 않고 흐름이 중단됩니다. 정지 이유는 진단에 기록됩니다.

> 현재 `__flow_control`은 `"abort"`만 지원합니다. 다른 값은 무시됩니다.

---

## 흐름 → HTTP 응답 매핑

Pack의 `routes.json`에 정의된 엔드포인트가 HTTP 요청을 받으면 Pack API 서버(`pack_api_server.py`)는 해당 Flow를 실행하고 그 결과를 HTTP 응답으로 변환하여 반환한다.

### 응답 변환 작동 방식

현재 구현에서는 Flow 실행 결과(`outputs`)가 **항상 JSON 형식으로 반환**됩니다. 응답은 `APIResponse` 데이터 클래스를 통해 생성됩니다.

```python
@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
```

흐름이 성공적으로 실행되는 경우:

```json
{
  "success": true,
  "data": { "...Flow outputs がここに入る..." },
  "error": null
}
```

흐름 실행이 실패하는 경우:

```json
{
  "success": false,
  "data": null,
  "error": "エラーメッセージ"
}
```

### 상태 코드

Pack API 서버의 `_send_response`은 다음 HTTP 상태 코드를 사용합니다.

| 상태 | 상태 코드 |
|------|-----------------|
| 흐름 실행 성공 | §루미§0§ |
| 인증 실패 | §루미§0§ |
| 잘못된 입력 | §루미§0§ |
| 경로를 찾을 수 없습니다 | §루미§0§ |
| 내부 오류 | §루미§0§ |

### 헤더

다음 헤더가 응답에 자동으로 추가됩니다.

| 헤더 | 가치 | 조건 |
|---------|-----|------|
| §루미§0§ | §루미§1§ | 항상 부여됨 |
| §루미§0§ | Origin에서 요청함 | CORS 허용 목록과 일치 |
| §루미§0§ | §루미§1§ | CORS 헤더를 추가할 때 |

### 특수키로 제어

`_status_code`, `_headers`, `_body`와 같은 특수 키를 사용한 HTTP 응답의 직접 제어는 현재 **지원되지 않습니다**. 흐름 출력은 항상 `APIResponse`의 `data` 필드에 저장되고 `application/json` 형식으로 반환됩니다.

사용자 정의 상태 코드 또는 헤더 제어가 필요한 경우 [HTTP 상태 코드 제어](#http-상태-코드-제어)를 참조하세요.

---

## 흐름 수정자

이는 나중에 기존 Flow에 기능을 삽입하기 위한 메커니즘입니다.

### 배치 경로

- §루미§0§
- §루미§0§

### 예

```yaml
# user_data/shared/flows/modifiers/add_logging.modifier.yaml

modifier_id: add_logging
target_flow_id: ai_response
phase: postprocess
priority: 90
action: inject_after
target_step_id: format_output

step:
  id: log_response
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log_ai_response.py
  input:
    response: "${ctx.response}"
```

### 사용 가능한 작업

| 액션 | 설명 |
|--------|------|
| §루미§0§ | 지정된 단계 앞에 삽입 |
| §루미§0§ | 지정된 단계 뒤에 삽입 |
| §루미§0§ | 단계 끝에 추가 |
| §루미§0§ | 지정된 단계 바꾸기 |
| §루미§0§ | 지정된 단계 삭제 |

> **단계 제약**: 수정자의 `phase`은 대상 흐름의 `phases` 목록에 포함되어야 합니다. 존재하지 않는 단계를 지정하면 수정자를 건너뜁니다.

> **적용 순서**: 수정자는 단계 → 우선 순위 → modifier_id별로 정렬되고 결정론적으로 적용됩니다. 동일한 주입점에 여러 개의 수정자가 있는 경우(`inject_before` / `inject_after` ~ 동일한 `target_step_id`), 우선순위 → step.id → modifier_id 순으로 한꺼번에 삽입하여 인덱스 이동으로 인한 비결정성을 방지합니다. `replace` / `remove`는 주입/추가 전에 적용됩니다.

### 와일드카드 target_flow_id

`target_flow_id`에서 와일드카드 패턴을 사용하여 동시에 여러 흐름에 수정자를 적용할 수 있습니다.

| 패턴 | 의미 |
|----------|------|
| §루미§0§ | 모든 흐름에 적용 |
| §루미§0§ | `my_pack.`으로 시작하는 모든 흐름에 적용 |

일치에는 Python의 `fnmatch`이 사용됩니다.

```yaml
modifier_id: global_logging
target_flow_id: "*"
phase: postprocess
priority: 99
action: append
step:
  id: global_log
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log.py
```

### 조건이 필요합니다

```yaml
requires:
  interfaces:
    - "ai.client"
  capabilities:
    - "tool_support"
```

조건이 충족되지 않으면 수정자를 건너뜁니다.

---

## 네트워크 접속

### 개요

팩은 Docker `--network=none`에 격리되어 있으며 외부와 직접 통신할 수 없습니다. 외부 통신에는 네트워크 부여가 필요하며 모든 요청은 송신 프록시(UDS 소켓)를 통과합니다.

### 블록 내부의 HTTP 요청

```python
def run(input_data, context=None):
    http_request = context.get("http_request")
    if not http_request:
        return {"error": "http_request not available"}

    result = http_request(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": "Bearer ...",
            "Content-Type": "application/json"
        },
        body='{"model": "gpt-4", "messages": [...]}',
        timeout_seconds=30.0
    )

    if result["success"]:
        return {"data": result["body"]}
    else:
        return {"error": result["error"]}
```

> **시간 초과 제한**: `timeout_seconds`의 최대값은 120초입니다. 120보다 큰 값은 120초로 잘립니다. 이 제한은 `rumi_syscall` 및 `rumi_capability` 모두에 적용됩니다.

### 접속 가능 여부를 사전 확인하세요

```python
def run(input_data, context=None):
    check = context.get("network_check")
    result = check("api.openai.com", 443)

    if not result["allowed"]:
        return {"error": result["reason"]}

    # 通信可能
```

### 보조금을 받는 방법

API를 통해 사용자 또는 운영자가 부여합니다. 자세한 내용은 [operations.md](./operations.md)의 ``네트워크 권한 관리''를 참조하세요.

---

## context["http_request"] 세부 사양

`python_file_call`의 `run(input_data, context)`에 전달된 `context["http_request"]`은 팩 코드가 외부 HTTP 통신을 할 수 있는 유일한 수단입니다.

### 함수 서명

```python
def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    ...
```

### 매개변수

| 매개변수 | 유형 | 기본값 | 설명 |
|------------|-----|-----------|------|
| §루미§0§ | §루미§1§ | (필수) | HTTP 메서드. §루미§2§, §루미§3§, §루미§4§, §루미§5§, §루미§6§, §루미§7§ |
| §루미§0§ | §루미§1§ | (필수) | 요청할 전체 URL |
| §루미§0§ | §루미§1§ | §루미§2§ | HTTP 요청 헤더 |
| §루미§0§ | §루미§1§ | §루미§2§ | 요청 본문(문자열). JSON을 보낼 때 `json.dumps()` 문자열 |
| §루미§0§ | §루미§1§ | §루미§2§ | 시간 초과(초) 최대 `120.0`초로 제한됨 |

### 반환값

성공 시:

```python
{
    "success": True,
    "status_code": 200,          # int: HTTPステータスコード
    "headers": {"Content-Type": "application/json", ...},  # dict: レスポンスヘッダー
    "body": "...",               # str: レスポンスボディ
    "latency_ms": 123.4,         # float: 所要時間（ミリ秒）
    "redirect_hops": 0,          # int: リダイレクト回数
    "bytes_read": 1024,          # int: 読み取りバイト数
    "final_url": "https://...",  # str: 最終URL（リダイレクト後）
}
```

실패 시:

```python
{
    "success": False,
    "error": "エラーメッセージ",     # str: エラー内容
    "error_type": "timeout",       # str: エラー種別
}
```

### error_type 목록

| 오류 유형 | 설명 |
|------------|------|
| §루미§0§ | 송신 프록시 소켓을 찾을 수 없습니다. |
| §루미§0§ | 소켓에 액세스할 수 있는 권한이 없습니다 |
| §루미§0§ | 송신 프록시에 대한 연결이 거부되었습니다 |
| §루미§0§ | 요청 시간이 초과되었습니다 |
| §루미§0§ | 프로토콜 수준 오류 |
| §루미§0§ | 응답의 JSON 구문 분석 실패 |
| §루미§0§ | 네트워크 부여로 인해 액세스가 거부되었습니다 |

### UDS 송신 프록시를 통한 통신

팩 코드의 모든 외부 HTTP 통신은 **UDS(Unix Domain Socket) 송신 프록시**를 통과합니다. 팩 코드는 직접적인 네트워크 통신을 할 수 없습니다.

커뮤니케이션 흐름:

```
Pack コード (run関数)
  → context["http_request"]()
    → UDS ソケット (/run/rumi/egress/packs/{pack_id}.sock)
      → Egress Proxy (Kernel 側)
        → Network Grant Manager でアクセス許可を検証
          → 許可されていれば外部 HTTP リクエストを実行
          → 拒否されていれば grant_denied エラーを返却
```

> 소켓 경로는 `RUMI_EGRESS_SOCK_DIR` 환경 변수로 변경할 수 있습니다. 기본값은 `/run/rumi/egress/packs`입니다.

### 컨테이너 모드와 호스트 모드의 차이점

| 아이템 | 컨테이너 모드(엄격) | 호스트 모드(허용) |
|------|--------------------------|---------------------------|
| 네트워크 | `--network=none`(완전격리) | 호스트 네트워크 사용 |
| 통신 경로 | UDS 소켓을 통해서만 | UDS 소켓을 통해(도우미 기능을 통해) |
| 소켓 경로 | `/run/rumi/egress/packs/{pack_id}.sock`(컨테이너 내부 마운트) | §루미§1§ |
| 승인된 보조금 | 송신 프록시 검증됨 | 송신 프록시 검증됨 |
| 보안 | Docker 격리 + UDS 제한 사항 | 경고와 함께 실행(프로덕션에는 권장되지 않음) |

컨테이너 모드(`RUMI_SECURITY_MODE=strict`)에서는 Docker 컨테이너가 `--network=none`으로 시작되므로 UDS 소켓 외에는 다른 통신 수단이 없습니다. 호스트 모드(`RUMI_SECURITY_MODE=permissive`)는 Docker 없이 실행되지만 `context["http_request"]`도 Egress Proxy를 통과하므로 네트워크 부여에 의한 제어가 효과적입니다.

### 사용예

```python
def run(input_data: dict, context: dict) -> dict:
    # GET リクエスト
    result = context["http_request"](
        method="GET",
        url="https://api.example.com/data",
        headers={"Accept": "application/json"},
        timeout_seconds=10.0,
    )

    if not result["success"]:
        return {"error": result["error"]}

    return {"status": result["status_code"], "body": result["body"]}
```

```python
def run(input_data: dict, context: dict) -> dict:
    import json

    # POST JSON リクエスト
    result = context["http_request"](
        method="POST",
        url="https://api.example.com/items",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"name": input_data.get("name")}),
        timeout_seconds=15.0,
    )

    if not result["success"]:
        return {"error": result["error"], "error_type": result.get("error_type")}

    return {"created": True, "response": result["body"]}
```

---

## 비밀 사용(Pack에서)

팩은 `secrets.get` 기능을 사용하여 비밀(예: API 키)을 얻습니다. 운영자가 비밀을 등록하고 권한을 부여한 후에 사용할 수 있게 됩니다.

### 사용예

```python
import rumi_capability

result = rumi_capability.call("secrets.get", args={"key": "OPENAI_API_KEY"})
if result["success"]:
    api_key = result["output"]["value"]
else:
    # "Access denied or secret not found"
    error = result["output"]["error"]
```

### 접근 제어

`secrets.get` 부여는 `grant_config.allowed_keys`에서 액세스할 수 있는 키를 명시적으로 지정해야 합니다. `allowed_keys`가 비어 있거나 지정되지 않은 경우 모든 키에 대한 액세스가 거부됩니다(페일클로즈).

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "my_pack",
    "permission_id": "secrets.get",
    "config": {"allowed_keys": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]}
  }'
```

### 중요 제약사항

- `get`는 능력을 통해서만 획득할 수 있습니다. 비밀 값을 직접 다시 표시하는 API가 없습니다.
- `secrets.get`에는 비율 제한이 적용됩니다. (기본값은 60회/분/팩, 환경변수 `RUMI_SECRET_GET_RATE_LIMIT`로 변경 가능, 슬라이딩 윈도우 방식)
- 값은 로그, 감사 또는 예외 메시지에 포함되지 않습니다.
- 키가 존재하는지 여부는 오류 메시지에서 확인할 수 없습니다("액세스가 거부되었거나 비밀을 찾을 수 없음"으로 통일).

---

## 기능 사용

Pack이 기능 처리기를 사용하려면(예: 파일 시스템 읽기, 외부 도구 실행 등) Pack에 적절한 권한 부여가 부여되어야 합니다.

### 신뢰와 부여의 관계

기능을 사용하려면 두 가지 수준의 승인이 필요합니다.

1. **신뢰 등록**(핸들러 인증): 핸들러 코드(sha256)를 신뢰할 수 있는 것으로 등록합니다.
2. **Grant**(허가 부여): 승인된 핸들러에게 Pack에 대한 권한을 부여합니다.

```
handler.py が信頼される（Trust 登録）
    ↓
Pack に permission が付与される（Grant 付与）
    ↓
Pack が capability を使用可能
```

신탁을 등록하더라도 부여 없이는 사용할 수 없습니다. 반대로, 승인이 있어도 트러스트가 등록되지 않은 핸들러는 실행할 수 없습니다.

### 기능 호출 방법

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})
if result["success"]:
    content = result["output"]
else:
    error = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
```

### 내장 기능 처리기

다음 기능 핸들러는 코어 런타임에 포함되어 있으며 신뢰 등록 없이도 사용할 수 있습니다(별도 부여 필요).

| 허가_ID | 핸들러_ID | 설명 | 위험 |
|---------------|-----------|------|------|
| §루미§0§ | §루미§1§ | 비밀 값 얻기 | 높다 |
| §루미§0§ | §루미§1§ | Store에서 값 읽기 | 낮음 |
| §루미§0§ | §루미§1§ | 저장소에 값 쓰기 | 매체 |
| §루미§0§ | §루미§1§ | 저장소에서 값 제거 | 매체 |
| §루미§0§ | §루미§1§ | 스토어에서 키 목록 가져오기 | 낮음 |
| §루미§0§ | §루미§1§ | 스토어에서 대량 검색(최대 100개 키) | 낮음 |
| §루미§0§ | §루미§1§ | Store Compare-And-Swap(낙관적 배타적 제어) | 매체 |
| §루미§0§ | §루미§1§ | 다른 Pack 구성 요소의 받은 편지함에 JSON 메시지 보내기 | 매체 |
| §루미§0§ | §루미§1§ | 다른 팩에 파일 변경 제안(스테이징 생성, 자동 적용 없음) | 높다 |
| §루미§0§ | §루미§1§ | 동기식 Flow-to-Flow 호출 | 매체 |
| §루미§0§ | §루미§1§ | Docker 컨테이너 실행 | — |
| §루미§0§ | §루미§1§ | Docker 컨테이너 내부의 명령 실행 | — |
| §루미§0§ | §루미§1§ | Docker 컨테이너 중지 | — |
| §루미§0§ | §루미§1§ | Docker 컨테이너 로그 획득 | — |
| §루미§0§ | §루미§1§ | 도커 컨테이너 목록 | — |

### 그랜트 그랜트

API를 사용하는 사용자 또는 운영자가 권한을 부여합니다. 자세한 내용은 [operations.md](./operations.md)의 ``능력 부여 관리''를 참조하세요.

```bash
# 例: store.get の Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["my_store"]}}'
```

### 부여 구성(grant_config)

보조금은 `config`에 설정된 한도를 가질 수 있습니다. 권한에 따라 설정이 다릅니다.

| 허가_ID | grant_config 키 | 설명 |
|---------------|-------------------|------|
| §루미§0§ | §루미§1§ | 액세스 가능한 키 이름 목록(필수, 비어 있으면 완전히 거부됨) |
| §루미§0§ | §루미§1§ | 접근 가능한 store_ids 목록(필수, 비어 있으면 완전히 거부됨) |
| §루미§0§ | §루미§1§ | 최대 쓰기 크기(바이트, 기본값 1MB) |

`allowed_keys` / `allowed_store_ids`은 페일클로즈됩니다. 목록이 비어 있거나 지정되지 않은 경우 모든 액세스가 거부됩니다.

### 오류 처리

Capability 호출이 실패하면 `success: False`이 포함된 사전이 반환됩니다.

```python
import rumi_capability

result = rumi_capability.call("fs.read", args={"path": "/data/config.json"})

if not result.get("success", False):
    error_type = result.get("error_type", "unknown")

    if error_type == "grant_denied":
        # Grant が付与されていない
        pass
    elif error_type == "trust_denied":
        # handler が信頼されていない
        pass
    elif error_type == "handler_not_found":
        # handler が存在しない
        pass
    elif error_type == "execution_error":
        # handler 実行中のエラー
        pass
    elif error_type == "timeout":
        # タイムアウト
        pass
```

| 오류 유형 | 설명 |
|------------|------|
| §루미§0§ | 팩에는 권한 부여가 없습니다 |
| §루미§0§ | 처리기의 sha256이 Trust Store에 등록되지 않았습니다. |
| §루미§0§ | 지정된 허가_ID에 해당하는 핸들러가 존재하지 않습니다 |
| §루미§0§ | 핸들러 실행 중 오류 발생 |
| §루미§0§ | 실행 시간이 초과되었습니다 |
| §루미§0§ | 기능 소켓을 찾을 수 없습니다 |

---

## Store API(기능을 통해)

### 개요

저장소는 팩 간에 공유할 수 있는 키-값 저장소입니다. 저장소 작업은 Capability를 통해 수행됩니다. 운영자가 팩에 기능 부여를 부여하면 액세스가 활성화됩니다.

### 사용 가능한 허가_id

| 허가_ID | 설명 | 인수 |
|---------------|------|------|
| §루미§0§ | 저장소에서 값 읽기 | §루미§1§, §루미§2§ |
| §루미§0§ | 저장소에 값 쓰기 | §루미§1§, §루미§2§, §루미§3§ |
| §루미§0§ | 저장소에서 값 제거 | §루미§1§, §루미§2§ |
| §루미§0§ | 스토어에서 키 목록 가져오기 | `store_id`, `prefix`(선택) |

### 사용예

```python
import rumi_capability

# 値の書き込み
result = rumi_capability.call("store.set", args={
    "store_id": "my_store",
    "key": "users/user_001",
    "value": {"name": "Alice", "role": "admin"}
})

# 値の読み取り
result = rumi_capability.call("store.get", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
if result["success"]:
    output = result["output"]
    if output.get("success"):
        user = output["value"]

# キー一覧
result = rumi_capability.call("store.list", args={
    "store_id": "my_store",
    "prefix": "users/"
})
```

> `store.list`의 `output`에는 `success`(bool) 및 `keys`(키 이름 배열)이 포함되어 있습니다.

```python
# 値の削除
result = rumi_capability.call("store.delete", args={
    "store_id": "my_store",
    "key": "users/user_001"
})
```

### 부여 설정

`store.*`의 보조금에는 `grant_config`에 설정된 제한이 있을 수 있습니다.

| grant_config 키 | 설명 | 기본값 |
|-------------------|------|-----------|
| §루미§0§ | 접근을 허용할 store_id 목록 | `[]` (목록이 비어 있으면 모든 스토어에 대한 접근이 거부됩니다. Store_id를 명시적으로 지정해야 접근 가능) |
| §루미§0§ | `store.set` 최대 크기(바이트) | 1MB(1048576) |

`allowed_store_ids`은 실패 시 닫힙니다. 보조금 생성 시 `allowed_store_ids`을 지정하지 않거나 빈 목록 `[]`을 지정하면 해당 보조금에 대해 모든 스토어에 대한 액세스가 거부됩니다. Pack이 Store에 액세스하려면 운영자는 store_id를 목록에 명시적으로 추가해야 합니다.

### 매장 만들기

저장소 생성은 운영 API를 사용하여 수행됩니다.

```bash
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "my_store", "root_path": "user_data/stores/my_store"}'
```

> **store_id 제약조건**: `store_id`은 `^[a-zA-Z0-9_-]{1,64}$`과 일치해야 합니다.

### 내장 기능 처리기 목록

다음 기능 핸들러는 코어 런타임에 포함되어 있으며 신뢰 등록 없이도 사용할 수 있습니다(별도 부여 필요).

| 허가_ID | 핸들러_ID | 설명 | 위험 |
|---------------|-----------|------|------|
| §루미§0§ | §루미§1§ | 비밀 값 얻기 | 높다 |
| §루미§0§ | §루미§1§ | Store에서 값 읽기 | 낮음 |
| §루미§0§ | §루미§1§ | 저장소에 값 쓰기 | 매체 |
| §루미§0§ | §루미§1§ | 저장소에서 값 제거 | 매체 |
| §루미§0§ | §루미§1§ | 스토어에서 키 목록 가져오기 | 낮음 |
| §루미§0§ | §루미§1§ | 스토어에서 대량 검색(최대 100개 키) | 낮음 |
| §루미§0§ | §루미§1§ | Store Compare-And-Swap(낙관적 배타적 제어) | 매체 |
| §루미§0§ | §루미§1§ | 다른 Pack 구성 요소의 받은 편지함에 JSON 메시지 보내기 | 매체 |
| §루미§0§ | §루미§1§ | 다른 팩에 파일 변경 제안(스테이징 생성, 자동 적용 없음) | 높다 |
| §루미§0§ | §루미§1§ | 동기식 Flow-to-Flow 호출 | 매체 |
| §루미§0§ | §루미§1§ | Docker 컨테이너 실행 | — |
| §루미§0§ | §루미§1§ | Docker 컨테이너 내부의 명령 실행 | — |
| §루미§0§ | §루미§1§ | Docker 컨테이너 중지 | — |
| §루미§0§ | §루미§1§ | Docker 컨테이너 로그 획득 | — |
| §루미§0§ | §루미§1§ | 도커 컨테이너 목록 | — |

---

## 팩 간 협력 패턴

### 공유 흐름을 사용한 배선

여러 팩의 블록은 `user_data/shared/flows/`에 있는 흐름을 사용하여 연결할 수 있습니다. 팩은 서로에 대해 알 필요가 없습니다.

```yaml
# user_data/shared/flows/ai_pipeline.flow.yaml
flow_id: ai_pipeline
phases:
  - prepare
  - generate
  - postprocess

steps:
  - id: load_capabilities
    phase: prepare
    priority: 50
    type: python_file_call
    owner_pack: capability_provider
    file: blocks/load_capabilities.py
    output: capabilities

  - id: generate
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      capabilities: "${ctx.capabilities}"
    output: response
```

### 스토어를 통한 데이터 전달

저장소를 사용하여 서로 다른 흐름에서 작동하는 팩 간에 데이터를 공유합니다.

```python
# Pack A: データを Store に書き込む
import rumi_capability

rumi_capability.call("store.set", args={
    "store_id": "shared_data",
    "key": "latest_result",
    "value": {"score": 0.95, "text": "..."}
})
```

```python
# Pack B: Store からデータを読み取る
import rumi_capability

result = rumi_capability.call("store.get", args={
    "store_id": "shared_data",
    "key": "latest_result"
})
if result["success"]:
    data = result["output"]["value"]
```

---

## lib(설치/업데이트)

### 개요

Pack이 초기화되거나 업데이트될 때 한 번만 실행되는 스크립트입니다. 정상적으로 실행되지 않습니다.

### 파일 구조

```
ecosystem/<pack_id>/backend/lib/
├── install.py    # 初回導入時に実行
└── update.py     # ハッシュ変更時に実行（なければ install.py が実行される）
```

### install.py 예

```python
def run(context=None):
    pack_id = context.get("pack_id") if context else "unknown"
    data_dir = context.get("data_dir") if context else None

    # data_dir 内に初期設定ファイルを作成
    if data_dir:
        import json, os
        config_path = os.path.join(data_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump({"initialized": True}, f)

    return {"status": "installed"}
```

### 상황에 따라 제공되는 정보

| 열쇠 | 설명 |
|------|------|
| §루미§0§ | 팩 ID |
| §루미§0§ | `"install"` 또는 `"update"` |
| §루미§0§ | 타임스탬프 |
| §루미§0§ | lib 디렉터리 경로(컨테이너 내부: `/lib`) |
| §루미§0§ | 쓰기 가능한 디렉터리(컨테이너 내: `/data`, 호스트: `user_data/packs/{pack_id}/`) |

### 보안 제약

엄격 모드에서는 Docker 컨테이너 내에서 격리되어 실행됩니다. §루미§0§, §루미§1§. 글쓰기는 `/data`(= `user_data/packs/{pack_id}/`)까지만 가능합니다.

---

## pip 종속성(requirements.lock)

### 개요

팩이 PyPI 패키지에 의존하는 경우 `requirements.lock`을 포함하세요.

### 배치 경로

다음 순서로 검색했습니다.

1. §루미§0§
2. `<pack_subdir>/backend/requirements.lock`(호환)

### 형식

`NAME==VERSION` 라인만 허용됩니다. 주석 라인과 빈 라인이 허용됩니다.

```
requests==2.31.0
flask==3.0.0
```

다음은 금지됩니다: `-e`, `git+`, `http://`, `https://`, `file:`, `../`, `/`, `--` 옵션 라인, `@` 직접 참조.

### 팩 코드의 사용법

승인 및 설치 후 평소처럼 `import`를 실행하세요.

```python
import requests  # pip で導入された依存

def run(input_data, context=None):
    resp = requests.get("https://api.example.com/data")
    return {"data": resp.json()}
```

실행 컨테이너에서는 사이트 패키지가 `/pip-packages:ro`로 마운트되고 `PYTHONPATH`에 추가됩니다.

### 승인을 받는 방법

사용자 또는 운영자가 API를 통해 승인합니다. 자세한 내용은 [operations.md](./operations.md)의 ``pip 종속성 라이브러리 관리''를 참조하세요.

---

## 권한.json

팩에 필요한 권한을 선언하는 파일입니다.

```json
{
  "pack_id": "my_pack",
  "permissions": [
    {
      "type": "network",
      "domains": ["api.example.com"],
      "ports": [443],
      "reason": "外部 API にアクセスするため"
    }
  ]
}
```

Permissions.json은 선언적이며 런타임에 적용되지 않습니다. 실제 액세스 제어는 기능 부여 및 네트워크 부여를 통해 수행됩니다. 이 파일은 사용자에게 정보를 제공하기 위한 것입니다(이 팩에 필요한 권한).

---

## 기능 처리기 포함

Pack이 기능 처리기를 제공하는 경우 다음 규칙을 따릅니다.

### 배치

```
ecosystem/<pack_id>/
└── backend/
    └── share/
        └── capability_handlers/
            └── <slug>/
                ├── handler.json
                └── handler.py
```

팩의 `pack_subdir`(보통 `ecosystem/<pack_id>/backend/`) 아래 `share/capability_handlers/<slug>/`에 넣으세요.

### handler.json

```json
{
  "handler_id": "fs_read_handler",
  "permission_id": "fs.read",
  "entrypoint": "handler.py:execute",
  "description": "ファイルシステム読み取り handler",
  "risk": "ファイルシステムへの読み取りアクセスを提供"
}
```

| 필드 | 필수 | 설명 |
|-----------|------|------|
| §루미§0§ | ✅ | 핸들러의 고유 식별자 |
| §루미§0§ | ✅ | 요청된 권한 ID |
| §루미§0§ | ✅ | 실행 진입점(예: `handler.py:execute`) |
| §루미§0§ | 선택사항 | 설명 |
| §루미§0§ | 선택사항 | 위험 설명 |

후보자는 스캔으로 감지되고 사용자가 승인한 후 `user_data/capabilities/handlers/<slug>/`에 복사됩니다. 승인은 Trust(sha256 허용 목록) 등록에만 적용되며, 별도로 Grant가 필요합니다.

> 위 방법은 기존 방식(호환)입니다. 새 팩에는 다음 기능/방법이 권장됩니다.

### 함수/메소드(권장)

팩이 기능 기능을 제공하는 경우 해당 기능을 `functions/` 디렉터리에 배치하세요.

#### 배치

```
ecosystem/<pack_id>/
└── backend/
    └── functions/
        └── <function_id>/
            ├── manifest.json
            └── main.py
```

#### 매니페스트.json

```json
{
  "function_id": "get",
  "description": "Read a value from a Store by key.",
  "requires": ["store.get"],
  "caller_requires": [],
  "host_execution": true,
  "tags": ["store", "read"],
  "risk": "low",
  "vocab_aliases": ["store.get"],
  "input_schema": {
    "type": "object",
    "required": ["store_id", "key"],
    "properties": {
      "store_id": { "type": "string" },
      "key": { "type": "string" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "success": { "type": "boolean" },
      "value": { "description": "The stored JSON value" }
    }
  },
  "calling_convention": "block"
}
```

| 필드 | 필수 | 설명 |
|-----------|------|------|
| §루미§0§ | ✅ | 기능 식별자 |
| §루미§0§ | 선택사항 | 기능 설명 |
| §루미§0§ | ✅ | 이 기능을 실행하는 데 필요한 허가_ID 목록(예: `["store.get"]`) |
| §루미§0§ | 선택사항 | 호출자에게 요청할 수 있는 추가 권한 목록 |
| §루미§0§ | 선택사항 | `true`인 경우 컨테이너 대신 호스트 프로세스에서 실행 |
| §루미§0§ | 선택사항 | 분류 태그 목록 |
| §루미§0§ | 선택사항 | 위험 수준(`low`, `medium`, `high`). docker type | 등 일부 함수에서는 생략됩니다.
| §루미§0§ | 선택사항 | 어휘 정규화에 사용되는 별칭 목록 |
| §루미§0§ | 선택사항 | JSON 스키마 입력 |
| §루미§0§ | 선택사항 | JSON 스키마 출력 |
| §루미§0§ | 선택사항 | Grant에 대한 기본 설정(docker 시스템에서 사용됨) |
| §루미§0§ | 선택사항 | 호출 규칙. `block` (기본값, core_pack 표준) = `execute(context, args)` 패턴 |

> **참고**: `permission_id` 필드는 매니페스트.json에 존재하지 않습니다. 권한을 지정하려면 `requires` 배열을 사용하세요.

#### 메인.py

```python
def execute(context: dict, args: dict) -> dict:
    """
    Args:
        context: 実行コンテキスト
            - grant_config: Grant 設定（allowed_store_ids 等）
        args: 入力引数（manifest.json の input_schema に対応）

    Returns:
        JSON 互換の dict
    """
    store_id = args.get("store_id", "")
    key = args.get("key", "")

    # ... 処理 ...

    return {"success": True, "value": result}
```

`calling_convention`가 `block`(기본값)인 경우 진입점은 `execute(context, args)`입니다. `context`에는 `grant_config`와 같은 실행 정보가 포함되어 있으며, `args`에는 Flow 단계의 `input`에 지정된 값이 전달됩니다.

---

## 어휘/변환기(고급)

> 일반적인 Pack 개발에서는 사용할 필요가 없습니다. 호환성 흡수를 위한 고급 기능.

### 어휘.txt

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

같은 줄에 쓰여진 단어는 동의어로 처리됩니다.

### 변환기

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

---

## 구성요소(고급)

Component는 `components/{component_id}/manifest.json`을 갖는 단위로 Lifecycle 관리(설정 등)에 사용됩니다. `python_file_call`에서는 컴포넌트를 특별히 취급하지 않으므로 `file` 필드에 상대 경로를 지정해 주십시오.

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

### setup.py의 기본 패턴

Component의 초기화 과정은 `components/{component_id}/setup.py`에 설명되어 있습니다.

```python
# ecosystem/my_pack/backend/components/my_component/setup.py

def setup(context=None):
    """
    Component 初期化時に呼ばれる。

    Args:
        context: 実行コンテキスト
            - interface_registry: InterfaceRegistry
            - event_bus: EventBus
            - diagnostics: Diagnostics
            - install_journal: InstallJournal

    Returns:
        任意の値（diagnostics に記録される）
    """
    ir = context.get("interface_registry") if context else None
    if ir:
        ir.register("my_component.ready", True)
    return {"status": "initialized"}
```

설정은 시작 시 `kernel:component.load` 단계에서 실행됩니다.

---

## 팩별 엔드포인트(routes.json)

### 개요

팩에는 HTTP API 서버에 자체 엔드포인트를 등록하기 위한 `routes.json`가 포함될 수 있습니다. 수신된 요청은 지정된 Flow를 실행하고 결과를 응답으로 반환합니다.

### 배치 경로

§루미§0§

### Routes.json 형식

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/api/my_pack/generate",
      "flow_id": "my_pack.generate",
      "description": "テキスト生成エンドポイント"
    },
    {
      "method": "GET",
      "path": "/api/orgs/{org_id}/tasks/{task_id}",
      "flow_id": "my_pack.get_task",
      "description": "タスク取得（パスパラメータ付き）"
    }
  ]
}
```

### 경로 매개변수

경로 매개변수는 `{param}` 표기법을 사용하여 정의할 수 있습니다. 경로 매개변수 값은 Flow의 `inputs`에 자동으로 포함됩니다.

예: `/api/orgs/{org_id}/tasks/{task_id}`를 요청하면 `inputs.org_id` 및 `inputs.task_id`가 각각의 값을 갖게 됩니다.

### 쿼리 매개변수 가져오기

GET 요청에 대한 쿼리 매개변수도 `inputs`에 포함되어 있습니다.

### Raw 본문/헤더 가져오기

Flow의 `inputs`에는 다음과 같은 특수 키도 포함되어 있습니다.

| 열쇠 | 설명 |
|------|------|
| §루미§0§ | 요청 본문의 base64 인코딩 값 |
| §루미§0§ | 요청 헤더의 사전 |
| §루미§0§ | HTTP 메소드(GET, POST 등) |
| §루미§0§ | 요청 경로 |

### 경로 재장전

```bash
curl -X POST http://localhost:8765/api/routes/reload \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 등록된 경로 확인

```bash
curl http://localhost:8765/api/routes \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## HTTP 상태 코드 제어

### 현재 사양

현재 Pack API 서버 구현에서는 **Pack이 Pack의 `routes.json` 엔드포인트에서 반환된 HTTP 상태 코드를 직접 제어하는 ​​것을 허용하지 않습니다.

Flow의 출력에 `_status_code`와 같은 특수 키를 포함하더라도 응답의 `data` 필드에만 포함되며 HTTP 상태 코드에는 반영되지 않습니다.

### 상태코드 판단 로직

Pack API 서버는 다음 논리를 사용하여 상태 코드를 결정합니다.

| 판결명령 | 상태 | 상태 코드 |
|--------|------|-----------------|
| 1 | 인증 실패 | §루미§0§ |
| 2 | 입력 유효성 검사 실패 | §루미§0§ |
| 3 | 경로를 찾을 수 없습니다 | §루미§0§ |
| 4 | 흐름 실행 성공 | `200`(고정) |
| 5 | Flow를 실행할 때 오류 dict가 반환됨 | `200`(데이터에 오류가 있지만 HTTP는 200) |
| 6 | Flow 실행 중 예외 발생 | §루미§0§ |

즉, 흐름이 성공적으로 완료되어 `{"error": "not found"}`을 반환하더라도 HTTP 상태 코드는 `200 OK`이 됩니다.

### 추천 패턴

현재 제약 조건에서는 응답 본문의 `success` 및 `error` 필드를 사용하여 클라이언트에게 오류를 전달합니다.

```python
def run(input_data: dict, context: dict) -> dict:
    item_id = input_data.get("id")
    if not item_id:
        return {"error": "missing id", "error_code": "MISSING_ID"}

    # ... 処理 ...

    if not found:
        return {"error": "item not found", "error_code": "NOT_FOUND"}

    return {"item": item_data}
```

클라이언트 측에서는 `data.error`의 유무에 따라 성공/실패가 결정됩니다.

### 향후 지원 예정

향후 버전에서는 Flow 출력에서 특수 키(`_status_code`, `_headers` 등)를 인식하고 이를 HTTP 응답에 반영하는 기능을 추가하는 것을 고려하고 있습니다.

---

## 오류 처리 모범 사례

### python_file_call의 run()에서 예외가 발생하는 경우

`run()` 함수 내에서 포착되지 않은 예외가 발생하면 실행 엔진은 다음을 수행합니다.

**컨테이너 모드**: Docker 프로세스가 0이 아닌 종료 코드로 종료되고 stderr의 내용이 오류 메시지로 기록됩니다. `ExecutionResult`의 `success`은 `False`가 되고, `error_type`은 `"container_execution_error"`가 됩니다.

**호스트 모드(허용)**: 예외는 `ThreadPoolExecutor`의 `Future`에서 전파되고 마찬가지로 `ExecutionResult`의 `success`는 `False`가 됩니다.

두 경우 모두 커널 처리기(`_h_python_file_call`)는 `_kernel_step_status: "failed"`을 반환합니다.

### 권장: try-Exception으로 래핑하고 오류 dict를 반환합니다.

예외가 누출되면 스택 추적만 기록되고 유용한 정보는 호출 Flow에 전달되지 않습니다. Try-Exception으로 래핑하고 구조화된 오류 정보를 반환해야 합니다.

```python
def run(input_data: dict, context: dict) -> dict:
    try:
        url = input_data["url"]
        result = context["http_request"](
            method="GET",
            url=url,
            timeout_seconds=input_data.get("timeout", 30),
        )

        if not result["success"]:
            return {
                "error": result["error"],
                "error_type": result.get("error_type", "unknown"),
            }

        return {"data": result["body"], "status_code": result["status_code"]}

    except KeyError as e:
        return {"error": f"missing required field: {e}"}
    except Exception as e:
        return {"error": str(e), "error_type": type(e).__name__}
```

### 흐름 단계 실패 시 동작

흐름의 한 단계가 실패할 때의 동작은 흐름 정의의 `defaults` 및 단계별 `on_error` 설정에 따라 결정됩니다.

| 설정 | 행동 |
|------|------|
| `defaults.fail_soft: true`(기본값) | 단계 실패를 기록하고 다음 단계로 진행 |
| §루미§0§ | 단계가 실패하면 전체 흐름을 중단합니다. |
| §루미§0§ | 이 단계가 실패하면 흐름 중단 |
| §루미§0§ | 이 단계가 실패하더라도 계속 |
| §루미§0§ | 대상을 비활성화하고 진행 |

흐름 수준 오류 처리기가 InterfaceRegistry에 `flow.error_handler`으로 등록되어 있으면 단계 예외가 발생할 때 해당 처리기가 호출됩니다. 오류 처리기는 `"abort"`(중단), `"retry"`(재시도) 또는 기타 항목(계속)을 반환하여 동작을 제어할 수 있습니다.

### Capability.call() 실패시 반환값 처리 방법

`rumi_capability` 모듈을 통해 Capability를 호출하면 `success: False`이 포함된 사전이 실패 시 반환됩니다.

```python
import rumi_capability

result = rumi_capability.call(
    "store.get",
    args={"store_id": "my_store", "key": "my_key"},
)

if not result.get("success", False):
    # エラー処理
    error_msg = result.get("error", "Unknown error")
    error_type = result.get("error_type", "unknown")
    return {"error": error_msg, "error_type": error_type}

# 成功時の処理
value = result.get("output", {}).get("value")
```

기능 호출이 실패할 수 있는 이유는 다음과 같습니다.

| 오류 유형 | 설명 |
|------------|------|
| §루미§0§ | 기능 사용이 승인되지 않음 |
| §루미§0§ | 기능 부여가 부여되지 않음 |
| §루미§0§ | Trust Store 확인 실패 |
| §루미§0§ | 지정된 기능 처리기가 존재하지 않습니다 |
| §루미§0§ | 핸들러를 실행하는 동안 오류가 발생했습니다 |
| §루미§0§ | 실행 시간이 초과되었습니다 |
| §루미§0§ | 기능 소켓을 찾을 수 없습니다 |

Try-Exception을 사용하는 대신 반환 값의 `success` 필드를 사용하여 이러한 오류를 확인하는 것이 좋습니다.

---

---

## Flow Modifier 권장 패턴

Flow Modifier는 강력한 기능이지만 처음부터 모든 작업을 사용하려고 하면 복잡해질 수 있습니다. 다음 두 가지 패턴으로 시작하는 것이 좋습니다.

### 패턴 1: 추가(단계 끝에 추가)

이것이 가장 안전하고 이해하기 쉬운 패턴입니다. 기존 Flow를 변경하지 않고 끝에 처리를 추가합니다.

```yaml
modifier_id: add_logging
target_flow_id: ai_response
phase: postprocess
priority: 90
action: append

step:
  id: log_response
  type: python_file_call
  owner_pack: logging_pack
  file: blocks/log_response.py
  input:
    response: "${ctx.response}"
```

사용 시기: 로깅, 감사, 알림, 사후 처리 추가

### 패턴 2: 교체(단계 교체)

이는 기존 단계의 구현을 대체하는 패턴입니다. 예를 들어 AI 클라이언트를 OpenAI에서 Anthropic으로 전환할 때 이를 사용합니다.

```yaml
modifier_id: swap_ai_client
target_flow_id: ai_response
phase: generate
priority: 50
action: replace
target_step_id: call_openai

step:
  id: call_anthropic
  type: python_file_call
  owner_pack: anthropic_client
  file: blocks/generate.py
  input:
    user_input: "${ctx.user_input}"
  output: ai_output
```

사용 시기: 구현 교체, 공급자 전환

### inject_before / inject_after를 사용해야 하는 경우

inject_before / inject_after는 특정 단계 전후에 처리를 삽입하고 싶을 때 사용됩니다. 그러나 대상 단계의 id에 의존하기 때문에 흐름 구조의 변화에 ​​취약하다. 다음과 같은 경우에만 사용을 고려하세요.

- 특정 단계의 입력 데이터를 사전 변환해야 하는 경우(inject_before)
- 특정 단계의 출력 데이터를 후처리해야 하는 경우(inject_after)
- 추가하기에는 실행 타이밍이 너무 느린 경우

### 제거는 최후의 수단입니다

제거는 기존 단계를 제거하고 흐름의 동작을 크게 변경할 수 있습니다. 일반적으로 대체 구현을 제공하는 것이 더 안전합니다.

---

## 핸들러 API 분류

커널이 제공하는 핸들러에는 "팩 개발자용"과 "내부 API"라는 두 가지 유형이 있습니다.

### 팩 개발자 API

Flow 정의에서 직접 사용할 수 있는 핸들러입니다. 안정적인 인터페이스가 보장됩니다.

| 핸들러 | 설명 | Flow에서 사용하는 방법 |
|---------|------|----------------|
| §루미§0§ | Python 파일 실행 | §루미§1§ |
| §루미§0§ | 하위 흐름 호출 | §루미§1§ |
| §루미§0§ | 실행 기능 기능 | §루미§1§ |
| §루미§0§ | 컨텍스트에 따라 값 설정 | §루미§1§ |
| §루미§0§ | 등록된 핸들러를 직접 호출 | §루미§1§ |

### 내부 API(Pack 개발자는 사용하지 않음)

내부 커널 작업에 사용되는 핸들러입니다. 팩 개발자는 이를 직접 호출할 필요가 없습니다.

| 카테고리 | 예 | 설명 |
|---------|-----|------|
| §루미§0§ | §루미§1§, §루미§2§ | 커널 내부의 컨텍스트 작업 |
| §루미§0§ | §루미§1§, §루미§2§ | 흐름 수명 주기 후크 |
| §루미§0§ | §루미§1§, §루미§2§ | Flow 구문의 내부 구현 |
| §루미§0§ | §루미§1§, §루미§2§ | 구성요소 수명주기 |

> **참고**: 내부 API는 예고 없이 변경될 수 있습니다. 팩의 흐름 정의에서 이를 직접 참조하지 마십시오.

---

## 출력 키 명명 규칙(자세히)

### 커널 내부 키 제외 규칙

Flow 실행 결과가 HTTP 응답으로 반환되면 다음 접두사로 시작하는 키는 **커널 내부 키**에서 자동으로 제외됩니다.

| 접두사 | 설명 |
|---------------|------|
| §루미§0§ | 흐름 제어 정보 |
| §루미§0§ | 커널 단계 메타데이터 |
| §루미§0§ | 단계 출력 내부 참조 |
| §루미§0§ | 현재 단계 번호 |
| §루미§0§ | 총 걸음수 |
| §루미§0§ | 상위 흐름 정보 |
| §루미§0§ | 집행자 ID |
| §루미§0§ | 흐름 제어 신호 |
| §루미§0§ | 오류 정보 |
| §루미§0§ | 흐름 기본값 |

### 팩 개발자가 `_` 접두사 키를 반환하는 경우

위에 나열된 커널 내부 접두사(예: `_debug`, `_my_internal`)와 **일치하지** 않는 `_` 접두사 키는 응답에서 제외되지 않습니다. 그러나 경고가 기록됩니다.

```python
# この例では _debug は除外されず、レスポンスに含まれる（警告ログ付き）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_debug": {"raw_response": "..."},  # 警告ログが出るがレスポンスに残る
    }
```

### 권장사항

- Pack 출력 키에 `_` 접두사를 사용하지 않는 것이 좋습니다.
- 디버그 정보를 포함하려면 `debug` 또는 `metadata`과 같은 일반 키 이름을 사용하세요.
- 커널 내부 접두사(예: `_flow_result`)와 일치하는 키 이름은 의도치 않게 제외되므로 특별히 피해야 합니다.

```python
# ✅ 推奨
def run(input_data, context=None):
    return {
        "result": "ok",
        "debug_info": {"raw_response": "..."},
        "metadata": {"source": "my_pack", "version": "1.0"},
    }

# ⚠️ 非推奨（動作はするが警告ログが出る）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_debug": {"raw_response": "..."},
    }

# ❌ 避けるべき（Kernel 内部キーとして除外される）
def run(input_data, context=None):
    return {
        "result": "ok",
        "_flow_result": "this will be silently removed",
        "_kernel_data": "this will also be removed",
    }
```


## 메모

- **InterfaceRegistry는 내부 API입니다. ** 팩에서 직접 IR을 작동하지 마십시오.
- **외부 통신은 Egress Proxy를 통해 이루어져야 합니다**. `context["http_request"]`를 사용하세요.
- **lib는 `/data`에만 쓸 수 있습니다. ** `--read-only`으로 인해 다른 경로에 쓰기가 실패합니다.
- **pack_identity를 변경하지 마십시오. ** 업데이트 중 `pack_identity`이 변경되면 신청이 거부됩니다.
- **principal_id는 v1의 owner_pack에 의해 강제로 덮어쓰기됩니다. ** Flow 정의나 Modifier에서 `principal_id`를 지정하더라도 런타임 시에는 `owner_pack` 값이 주체로 사용됩니다. 불일치가 감지되면 감사 로그에 경고가 기록됩니다.
- **응답 크기 제한 정보**: Egress Proxy(`rumi_syscall`) 및 Capability Client(`rumi_capability`)의 응답 제한은 4MB입니다(`RUMI_MAX_RESPONSE_BYTES`에서 변경 가능). 그러나 Capability Executor(서버 측 하위 프로세스 실행)의 응답 제한은 1MB입니다.
- **store.set의 기본 값 크기 제한은 1MB입니다. ** Grant의 `grant_config.max_value_bytes`로 변경될 수 있습니다.
- **FlowScheduler의 최소 간격 값은 10초입니다. ** 10초 미만으로 지정하시면 다음 10초로 반올림됩니다.
- **Flow 동시 실행의 기본 개수는 10개입니다. ** `RUMI_MAX_CONCURRENT_FLOWS` 환경 변수를 사용하여 변경할 수 있습니다.
- **기능 실행 시간 초과 제한은 120초입니다. ** `rumi_capability.call()`의 `timeout_seconds`에 120보다 큰 값을 지정하더라도 120초로 제한됩니다. 기본값은 30초입니다.

### 하드 링크는 지원되지 않습니다.

Pack 디렉터리(`ecosystem/<pack_id>/`) 내의 하드 링크 사용은 **지원되지 않습니다**.

#### 이유

팩 인증/해시 확인 시스템은 `Path.resolve()`으로 정규화된 파일 경로를 캐시 키로 사용합니다. 심볼릭 링크는 `resolve()`에 의해 실제 경로로 해석되므로 소스와 대상이 동일한 캐시 항목으로 결합됩니다. 반면, 하드 링크는 `resolve()`에서 통합되지 않습니다(각 경로 항목은 독립적으로 유지됩니다). 따라서 동일한 inode를 가리키는 여러 경로는 별도의 캐시 항목으로 처리되며 한 경로를 통한 파일 변경 사항은 다른 경로의 해시 유효성 검사에 반영되지 않을 수 있습니다.

```
hardlink_a.py ─┐
               ├─ 同一 inode → 内容は同一
hardlink_b.py ─┘

Path.resolve():
  hardlink_a.py → /abs/path/hardlink_a.py  ← キャッシュキー A
  hardlink_b.py → /abs/path/hardlink_b.py  ← キャッシュキー B（別エントリ）

symlink.py → target.py:
  symlink.py → /abs/path/target.py         ← target.py と同一キー ✓
```

#### 권장 대안

- **기호 링크**: `resolve()`의 실제 경로로 확인되어 해시 유효성 검사와 일관성을 유지합니다. 그러나 심볼릭 링크의 참조 대상은 **pack_subdir 경계 내**로 제한됩니다. 경계 외부를 가리키는 기호 링크는 런타임 시 거부됩니다.
- **파일 복사**: 가장 안전한 방법입니다. 각 파일에는 독립적인 해시가 있으며 확인 문제가 없습니다.

---

## API 참조

### rumi_syscall (외부 통신)

컨테이너 내에서 외부 HTTP 통신을 수행하기 위한 모듈입니다. `import rumi_syscall`에서 사용됩니다.

| 기능 | 설명 |
|------|------|
| §루미§0§ | 일반 HTTP 요청 |
| §루미§0§ | 바로가기 받기 |
| §루미§0§ | POST 바로가기 |
| §루미§0§ | JSON POST 단축키(Content-Type 자동 설정) |
| §루미§0§ | PUT 바로가기 |
| §루미§0§ | 삭제 단축키 |
| §루미§0§ | 패치 바로가기 |
| §루미§0§ | 헤드 바로가기 |

반환 값은 `success`(bool), `status_code`(int), `headers`(dict), `body`(str), `error`(str), `error_type`(str), `latency_ms`(float), `redirect_hops`(int), `bytes_read`(int), `final_url`를 포함하는 dict입니다. (str) 등

`request`는 `http_request`의 별칭입니다. `rumi_syscall.request(...)`도 동일한 동작을 합니다.

### rumi_capability (능력 호출)

컨테이너 내에서 Capability를 호출하기 위한 모듈입니다. `import rumi_capability`에서 사용됩니다.

| 기능 | 설명 |
|------|------|
| §루미§0§ | 실행 능력 |

반환 값은 `success`(bool), `output`(Any), `error`(str), `error_type`(str), `latency_ms`(float)을 포함하는 사전입니다.

```python
import rumi_capability

result = rumi_capability.call("store.get", args={"store_id": "my_store", "key": "config"})
if result["success"]:
    data = result["output"]
```

---

## 튜토리얼: 간단한 팩 만들기

외부 API에서 데이터를 검색하여 Store에 저장하고 HTTP 엔드포인트를 통해 반환하는 팩을 만듭니다.

### 1. 디렉토리 구조

```
ecosystem/weather_pack/
└── backend/
    ├── ecosystem.json
    ├── routes.json
    ├── blocks/
    │   ├── fetch_weather.py
    │   └── get_cached_weather.py
    └── flows/
        ├── fetch_weather.flow.yaml
        └── get_weather.flow.yaml
```

### 2. 생태계.json

```json
{
  "pack_id": "weather_pack",
  "pack_identity": "github:author/weather_pack",
  "version": "1.0.0",
  "description": "天気情報を取得・キャッシュする Pack"
}
```

### 3. 차단: fetch_weather.py

```python
import rumi_syscall
import rumi_capability

def run(input_data, context=None):
    city = input_data.get("city", "Tokyo")

    # 外部 API からデータ取得（Network Grant 必要）
    result = rumi_syscall.get(
        f"https://api.example.com/weather?city={city}",
        timeout_seconds=10.0
    )
    if not result["success"]:
        return {"error": result["error"]}

    import json
    weather = json.loads(result["body"])

    # Store に保存（store.set Grant 必要）
    rumi_capability.call("store.set", args={
        "store_id": "weather_cache",
        "key": f"weather/{city}",
        "value": weather
    })

    return {"weather": weather}
```

### 4. 차단: get_cached_weather.py

```python
import rumi_capability

def run(input_data, context=None):
    city = input_data.get("city", "Tokyo")

    result = rumi_capability.call("store.get", args={
        "store_id": "weather_cache",
        "key": f"weather/{city}"
    })

    if result["success"] and result["output"].get("success"):
        return {"weather": result["output"]["value"]}
    return {"error": "No cached data"}
```

### 5. 흐름 정의

```yaml
# flows/fetch_weather.flow.yaml
flow_id: weather_pack.fetch
schedule:
  interval: 300
phases:
  - main
steps:
  - id: fetch
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: weather_pack
    file: blocks/fetch_weather.py
    input:
      city: "Tokyo"
    output: result
```

```yaml
# flows/get_weather.flow.yaml
flow_id: weather_pack.get
phases:
  - main
steps:
  - id: get_cached
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: weather_pack
    file: blocks/get_cached_weather.py
    input:
      city: "${ctx.city}"
    output: result
```

### 6. 경로.json

```json
{
  "routes": [
    {
      "method": "GET",
      "path": "/api/weather/{city}",
      "flow_id": "weather_pack.get",
      "description": "キャッシュ済みの天気情報を返す"
    }
  ]
}
```

### 7. 운영 절차

```bash
# Pack を承認
curl -X POST http://localhost:8765/api/packs/weather_pack/approve \
  -H "Authorization: Bearer YOUR_TOKEN"

# Network Grant を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "weather_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'

# Store を作成
curl -X POST http://localhost:8765/api/stores/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "weather_cache", "root_path": "user_data/stores/weather_cache"}'

# Capability Grant を付与
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "weather_pack", "permission_id": "store.set", "config": {"allowed_store_ids": ["weather_cache"]}}'

curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "weather_pack", "permission_id": "store.get", "config": {"allowed_store_ids": ["weather_cache"]}}'

# 天気情報を取得
curl http://localhost:8765/api/weather/Tokyo \
  -H "Authorization: Bearer YOUR_TOKEN"
```
# Defaultspack 함수 계약

Defaultspack 기능은 Rumi 기능으로 사용할 수 있습니다. HTTP 경로나 defaultspack 파일 경로에 의존하는 대신 `defaults.ai.complete`, `defaultspack.chat.send` 또는 `defaultspack.ai.set_thinking_level`와 같은 별칭 호출을 선호합니다. 예시, 권한, AI 도구 래퍼 지침은 [defaultspack-functions.md](defaultspack-functions.md)을 참조하세요.
