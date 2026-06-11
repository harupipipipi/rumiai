<!-- docs-i18n-links:start -->
[EN](../../architecture.md) | [JP](../ja/architecture.md) | [KR](./architecture.md) | [CN](../zh-cn/architecture.md)
<!-- docs-i18n-links:end -->

# 루미 AI OS — 아키텍처

전반적인 디자인과 메커니즘을 설명하는 문서입니다. 팩 개발자의 경우 [pack-development.md](./pack-development.md), 운영자의 경우 [operations.md](./operations.md)도 참조하세요.

---

## 목차

1. [디자인 원칙](#디자인-원칙)
2. [플로우 시스템](#흐름-시스템)
3. [python_file_call](#python_file_call)
4. [흐름 수정자](#흐름-수정자)
5. [보안 모델](#보안-모델)
6. [팩 승인](#팩-승인)
7. [네트워크 권한 및 송신 프록시](#네트워크-권한-및-송신-프록시)
8. [역량체계(신뢰+부여)](#역량체계신뢰-부여)
9. [UDS 소켓 권한](#uds-소켓-권한)
10. [계층적 권한](#hierarchy-authority)
11. [비밀](#비밀)
12. [공유 사전](#공유-사전)
13. [lib 시스템](#lib-시스템)
14. [pip 종속 라이브러리 소개](#pip-dependency-library-installation)
15. [Pack Import / Apply](#pack-import--apply)
16. [컴포넌트 개념](#구성요소-개념)
17. [vocab / converter](#vocab--converter)
18. [감사 기록](#감사-로그)
19. [수출 보류 중](#내보내기-보류-중)
20. [DI 컨테이너 및 서비스 목록](#di-container-and-service-list)
21. [커널 믹스인 구성](#커널-믹스인-구성)
22. [관측성](#관찰-가능성)
23. [공통 인프라 모듈](#공통-기본-모듈)
24. [팩 개발 도구](#팩-개발-도구)
25. [지원 중단된 기능](#더-이상-사용되지-않는-기능)

---

## 디자인 원칙

### 편애 금지

공식 코어에는 도메인 개념(채팅, 도구, 프롬프트, AI 클라이언트, 프런트엔드 등)이 없습니다. 공식이 제공하는 것은 범용 실행 플랫폼입니다.

공식적으로 제공되는 메커니즘은 흐름 실행, 인증 게이트(해시 유효성 검사), 격리된 실행(Docker/UDS), 신뢰 + 부여(기능) 및 감사 로그로 제한됩니다.

### 악의적인 가정(위협 모델)

팩 작성자가 악의적인 의도를 갖고 있을 가능성을 항상 가정하십시오. 팩 실행은 일반적으로 Docker `--network=none`에서 격리됩니다. 외부 통신 및 호스트 권한은 기능(신뢰 + 부여)에 따라 조정되며 명시적인 허가 없이는 작동하지 않습니다.

### 페일소프트

한 부분이 고장나도 OS 전체가 멈추지 않습니다. 실패한 구성 요소는 비활성화되고 계속하려면 진단 및 감사에 기록됩니다.

### 호스트 권한을 위한 단일 진입점

호스트의 위험한 것(외부 통신, 파일 액세스, 업데이트 응용 프로그램 등)은 Pack에서 직접 실행되지 않고 기능에 의해 조정됩니다. 허락하지 않으면 움직이지 않습니다.

---

## 흐름 시스템

### 개요

Flow는 Pack 간의 연결 및 실행 순서를 정의하는 YAML 파일입니다. 각 흐름은 단계와 단계로 구성됩니다.

### 플로우 파일 형식

```yaml
flow_id: ai_response
inputs:
  user_input: string
  context: object
outputs:
  response: string

phases:
  - prepare
  - generate
  - postprocess

defaults:
  fail_soft: true
  on_missing_step: skip

steps:
  - id: load_context
    phase: prepare
    priority: 10
    type: handler
    input:
      handler: "kernel:ctx.get"
      args:
        key: "context"

  - id: call_ai
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      user_input: "${ctx.user_input}"
    output: ai_response
```

### 플로우 소스

플로우는 다음 순서로 로드됩니다. 동일한 `flow_id`의 경우 우선순위가 더 높은 것이 승리합니다(낮은 소스는 더 높은 소스의 플로우를 덮어쓸 수 없습니다).

| 우선순위 | 경로 | 사용법 | 승인 |
|--------|------|------|------|
| 1 | `flows/` | 공식 흐름(스타트업/베이스) | 필요하지 않음 |
| 2 | `user_data/shared/flows/` | 사용자/외부 도구에 의해 배치된 공유 흐름 | 필요하지 않음 |
| 3 | `ecosystem/<pack_id>/backend/flows/` | Pack에서 제공하는 흐름 | 팩 승인 필요 |
| 4 | `ecosystem/flows/`(더 이상 사용되지 않음) | local_pack 호환 흐름 | `RUMI_LOCAL_PACK_MODE=require_approval`인 경우에만 유효합니다. 승인 필요 |

재정의 규칙: 공식 흐름은 누구도 덮어쓸 수 없습니다. 공유 흐름은 공식 흐름을 재정의할 수 없지만 팩 제공 흐름보다 우선합니다. 팩 제공 흐름은 공식적이든 공유적이든 덮어쓸 수 없습니다. local_pack은 우선순위가 가장 낮으며 다른 소스를 재정의할 수 없습니다.

### 단계 유형

| 유형 | 설명 |
|------|------|
| `handler` | 커널 핸들러 호출 |
| `python_file_call` | Pack에서 Python 파일 실행 |
| `set` | 컨텍스트에 따라 값 설정 |
| `if` | 조건부 분기(간소화된 버전) |
| `function` | FunctionRegistry(Wave 27)에 등록된 기능 실행 |
| `flow` | 다른 흐름을 하위 흐름으로 호출 |

### 실행 순서

단계는 다음 순서로 결정적으로 정렬됩니다.

1. `phase` (`phases` 배열 정렬 순서)
2. `priority`(오름차순, 작은 것이 먼저 실행됨)
3. `id` (알파벳순. 타이브레이크)

### 변수 참조

```yaml
input:
  user_id: "${ctx.user.id}"     # ネスト参照
  settings: "${ctx.config}"      # オブジェクト全体
```

참조 대상이 존재하지 않으면 `null`(fail-soft)로 처리됩니다.

---

## python_file_call

### 개요

흐름의 단계로 팩의 Python 파일을 실행합니다. 입력을 받아 JSON 호환 출력을 반환하는 "블록"입니다.

### 블록 파일 형식

```python
# ecosystem/<pack_id>/backend/blocks/my_block.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ
        context: 実行コンテキスト
            - flow_id, step_id, phase, ts
            - owner_pack
            - inputs
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> ProxyResponse

    Returns:
        JSON 互換の出力データ
    """
    return {"message": "Hello from my_block!"}
```

### 경로 확인

`python_file_call`의 `file` 필드는 pack_subdir을 기준으로 확인됩니다. 다음 후보자를 순서대로 검색합니다.

1. `<pack_subdir>/blocks/`
2. `<pack_subdir>/backend/blocks/`
3. `<pack_subdir>/backend/components/`(호환)
4. `<pack_subdir>/backend/` (호환: 직접 설치)
5. `<pack_subdir>/<file>`(최종 대체)

모든 후보는 pack_subdir 경계 내로 제한됩니다. 경계 외부의 파일은 실행이 거부됩니다.

### 보안 점검(실행 전)

1. `owner_pack` 승인
2. `owner_pack`의 해시가 일치해야 합니다(수정되지 않음).
3. 파일 경로는 pack_subdir 경계 내에 있어야 합니다.

### Principal_id 처리(v1)

v1에서는 `principal_id`가 항상 `owner_pack`에 의해 강제로 덮어쓰기됩니다. Flow 정의에 `principal_id`를 지정하더라도 런타임에는 `owner_pack`이 사용됩니다. 이는 직권남용을 방지하기 위한 조치이다. 경고는 감사 로그에 `principal_id_overridden`로 기록됩니다.

---

## 흐름 수정자

### 개요

이는 나중에 기존 흐름에 단계를 삽입, 교체 또는 삭제할 수 있는 메커니즘입니다. 수정자를 사용하면 팩이 서로 모르는 경우에도 기능을 연결할 수 있습니다.

### 수정자 파일 형식

```yaml
modifier_id: tool_inject
target_flow_id: ai_response
phase: prepare
priority: 50
action: inject_after
target_step_id: load_context

requires:
  capabilities:
    - tool_support
  interfaces:
    - tool.registry

step:
  id: inject_tools
  type: python_file_call
  owner_pack: capability_provider
  file: blocks/capability_selector.py
  input:
    context: "${ctx.context}"
  output: selected_capabilities
```

### 수정자 배치 경로

수정자는 파일 이름 `*.modifier.yaml`으로 아래에 배치되어야 합니다.

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/`(팩에서 제공하는 경우)

### 액션

| 액션 | 설명 | 타겟_단계_ID | 단계 |
|--------|------|----------------|------|
| `inject_before` | 지정된 단계 앞에 삽입 | 필수 | 필수 |
| `inject_after` | 지정된 단계 뒤에 삽입 | 필수 | 필수 |
| `append` | 단계 끝에 추가됨 | 필요하지 않음 | 필수 |
| `replace` | 지정된 단계 바꾸기 | 필수 | 필수 |
| `remove` | 지정된 단계 삭제 | 필수 | 필요하지 않음 |

### 조건이 필요합니다

```yaml
requires:
  interfaces:
    - "ai.client"           # InterfaceRegistry に登録されているか
  capabilities:
    - "tool_support"        # capability が有効か
```

조건이 충족되지 않으면 수정자를 건너뜁니다(페일소프트).

### 신청 순서

1. `phase` 주문
2. `priority` 오름차순
3. `modifier_id` 오름차순

### solve_target(공유 사전으로 해결)

```yaml
modifier_id: compat_modifier
target_flow_id: old_flow_name
resolve_target: true              # オプトイン
resolve_namespace: "flow_id"      # デフォルト
```

`resolve_target: true`을 지정하면 `target_flow_id`이 적용되기 전에 공유 사전에서 해결됩니다.

---

## 보안 모델

### 보안 모드

환경 변수 `RUMI_SECURITY_MODE`으로 설정합니다.

| 모드 | 도커 | 행동 |
|--------|--------|------|
| `strict`(기본값) | 필수 | Docker를 사용할 수 없는 경우 실행 거부 |
| `permissive` | 필요하지 않음 | 경고와 함께 호스트 실행 허용(개발용) |

### 보호 메커니즘 목록

| 메커니즘 | 설명 |
|------|------|
| 승인 게이트 | 승인되지 않은 팩의 코드는 실행되지 않습니다 |
| 해시 검증 | 승인 후 파일 수정시 자동 무효화 |
| HMAC 서명 | 그랜트 파일 변조 감지됨 |
| 경로 제한 | pack_subdir 경계 외부의 파일 실행 거부 |
| 도커 격리 | `--network=none`, `--cap-drop=ALL`, `--read-only` |
| 송신 프록시(UDS) | 팩별 허용 목록으로 외부 통신 제어 |
| UDS 그룹 추가 | 전용 GID로 소켓 권한 관리 |
| 감사 로그 | 모든 작업을 기록 |
| 요구 사항.잠금 확인 | 공급망 공격 예방 |
| pack_신원 확인 | 팩 업데이트 시 혼동 방지 |
| DNS 리바인딩 조치 | DNS 확인 결과에 대한 내부 IP 검사 |

### 위협과 대응책

| 위협 | 대책 |
|------|------|
| 악성코드 실행 | 승인 필요 + Docker 격리 |
| 파일 변조 | SHA-256 해시 검증 |
| 설정 변조 | HMAC 서명 |
| 잘못된 외부 통신 | 송신 프록시 + 허용 목록 |
| 권한 승격 | 팩별 명시적 부여 |
| 공급망 공격 | 요구 사항.잠금 구문 제한 + 휠 전용 |
| 팩 혼동 | pack_identity 비교에 의해 거부됨 |
| DNS 리바인딩 | 해결 결과 내부 IP 점검 |

---

## 팩 승인

### 승인 흐름

```
Pack 配置 (ecosystem/<pack_id>/)
    ↓
メタデータのみ読み込み（コード実行なし）
    ↓
ユーザー承認
    ↓
全ファイルの SHA-256 ハッシュを記録
    ↓
初めてコード実行可能に
```

### 승인 상태

| 상태 | 코드 실행 | 설명 |
|------|-----------|------|
| `installed` | ❌ | 배치됨, 승인되지 않음 |
| `pending` | ❌ | 승인을 기다리는 중 |
| `approved` | ✅ | 승인됨 |
| `running` | ✅ | 승인 및 실행 중 |
| `modified` | ❌ | 승인 후 파일 변경 감지 |
| `blocked` | ❌ | 거부됨 |
| `error` | ❌ | 오류발생(승인처리 실패 등) |

파일 수정으로 인해 `modified` 상태가 발생하면 코드 실행 및 네트워크 권한이 자동으로 비활성화됩니다. 재승인이 필요합니다.

### 팩 보관 경로

팩은 다음 경로 중 하나에 배치할 수 있습니다.

| 경로 | 유형 | 설명 |
|------|------|------|
| `ecosystem/<pack_id>/` | **권장** | `paths.py`은 탐사의 최우선 순위입니다 |
| `ecosystem/packs/<pack_id>/` | 레거시 | 권장경로와 중복되면 무시 |

`paths.py`의 `discover_pack_locations()`에서는 `ecosystem/*`를 먼저 검색한 후 호환 경로로 `ecosystem/packs/*`를 검색합니다. 동일한 `pack_id`가 둘 다에 존재하는 경우 `ecosystem/<pack_id>/`가 우선합니다.

---

## 네트워크 권한 및 송신 프록시

### 디자인

팩은 외부와 직접 통신할 수 없습니다(Docker `--network=none`). 모든 외부 통신은 UDS 소켓을 통해 송신 프록시를 통과합니다.

```
Pack (network=none) → UDS Socket → Egress Proxy → 外部 API
                                        ↓
                                  network grant 確認
                                        ↓
                                    監査ログ記録
```

### UDS 기반 팩 식별

각 팩마다 UDS 소켓이 생성되며, `pack_id`은 소켓 경로에서 결정됩니다. 요청 페이로드의 `owner_pack` 필드는 무시됩니다(보안 조치).

### 네트워크 부여

```json
{
  "pack_id": "my_pack",
  "enabled": true,
  "allowed_domains": ["api.openai.com", "*.anthropic.com"],
  "allowed_ports": [443],
  "granted_at": "2024-01-01T00:00:00Z",
  "granted_by": "user",
  "_hmac_signature": "..."
}
```
도메인 일치는 정확한 일치(`api.openai.com`) 및 와일드카드(`*.anthropic.com`)를 지원합니다. 하위 도메인을 허용하려면 와일드카드 형식을 사용하여 명시적으로 지정하세요.

### 송신 프록시 방어 메커니즘

내부 IP 금지(localhost/private/link-local/CGNAT/멀티캐스트 등), DNS 리바인딩 조치(해결 결과가 내부 IP인 경우 거부), 리디렉션 제한(3홉, 각 홉마다 재확인 승인), 요청/응답 크기 제한(1MB/4MB), 타임아웃 제한(최대 120초), 헤더 수/크기 제한, 메서드 제한(GET, HEAD, POST, PUT, DELETE, PATCH).

### 웨이브 12~14 확장

#### 비율 제한(egress_rate_limiter.py)

Wave 12에 추가되었습니다. 팩당 토큰 버킷으로 요청 속도 제한을 제공합니다. 송신 프록시는 요청을 수락하기 전에 버킷을 검사하고 버킷이 고갈되면 `429`를 반환합니다.

#### 도메인 제어(egress_domain_controller.py)

Wave 12에 추가되었습니다. 허용 목록 외에도 도메인별로 세분화된 제어(차단 목록, 와일드카드 패턴)를 제공합니다.

#### 세분화된 시간 초과

Wave 12에 추가되었습니다. 이제 각 도메인에 대해 연결 시간 제한 및 읽기 시간 제한을 설정할 수 있습니다. 이전 전역 제한(120초)은 대체적으로 유지됩니다.

#### 모듈분할(Wave 13)

Wave 13에서는 송신 프록시 구현을 다음 모듈로 나누었습니다. 보안 점검이 수행되는 순서도 IP 검사 → 프로토콜 검사 → 도메인 검사 → 비율 제한의 순서로 구성 및 평가됩니다.

| 모듈 | 책임 |
|-----------|------|
| `egress_ip.py` | 내부 IP 점검, DNS 리바인딩 대책 |
| `egress_protocol.py` | 프로토콜 메소드 헤더 검사 |
| `egress_rate_limiter.py` | 팩 단위 비율 제한 |
| `egress_domain_controller.py` | 도메인 허용 목록/차단 목록 제어 |

#### 중복 코드 제거(W14-FIX)

Wave 14에서는 분할 후 모듈 간에 남아 있던 중복 코드(IP 검사 로직 등)를 제거하고 단일 책임을 보장했습니다.

---

## 역량체계(신뢰 + 부여)

### 개요

이는 Pack에서 제공하는 기능 처리기를 승인하고 프로덕션에 배치하며 주체에게 사용 권한(허용)을 부여하는 메커니즘입니다. 신탁과 보조금은 독립적으로 관리됩니다.

- **신뢰**: `handler_id` + `sha256`의 허용 목록. handler.py의 내용을 신뢰할 수 있는지 확인
- **지원**: `principal_id` × `permission_id` 지원. 누가 어떤 기능을 사용할 수 있는지 관리

### 전체적인 흐름

```
候補配置 (ecosystem/<pack_id>/share/capability_handlers/<slug>/)
    ↓
scan（候補検出）
    ↓
pending（承認待ち）
    ↓
approve（Trust 登録 + コピー + Registry reload）
    ↓
Grant 付与（principal × permission）
    ↓
使用可能
```

승인은 신뢰만을 등록합니다. 실제 사용을 위해서는 별도의 보조금이 필요합니다.

### 후보 상태 전환

| 조건 | 설명 |
|------|------|
| `pending` | 후보자 감지 및 승인 대기 중 |
| `installed` | 승인되었습니다. 신탁등록+복사완료 |
| `rejected` | 거부되었습니다. 쿨다운(1시간) 후 스누즈 가능 |
| `blocked` | 3번의 거부가 있는 자동 블록입니다. 차단 해제될 때까지 알림을 받지 않음 |
| `failed` | 승인 과정 중 오류 발생 |

### Candidate_key

후보자 신원은 `candidate_key`에서 관리됩니다:

```
{pack_id}:{slug}:{handler_id}:{sha256}
```

sha256을 포함함으로써 handler.py의 내용이 변경되면 다른 후보로 처리됩니다.

### TOCTOU 조치

승인시 handler.py의 sha256을 다시 계산하여 스캔시 값과 비교합니다. 일치하지 않는 경우 승인이 실패합니다.

### 복사하여 덮어쓰기

승인 시 `ecosystem/` 측의 후보자가 `user_data/capabilities/handlers/<slug>/`으로 복사됩니다. 생태계 측면은 분포 형태로 유지되며 이동되지 않습니다. 복사 대상에 핸들러가 이미 존재하고 handler_id 또는 sha256이 다른 경우 오류가 발생합니다(자동 덮어쓰기 금지).

### 모듈분할(Wave 13)

Wave 13에서는 기능 관련 모델과 로더가 다음 모듈로 나누어졌습니다.

| 모듈 | 책임 |
|-----------|------|
| `capability_models.py` | 기능 관련 데이터 모델 정의 |
| `flow_modifier_models.py` | Flow Modifier 관련 데이터 모델 정의 |
| `flow_modifier_loader.py` | 수정자 파일 로드/파싱 |

### 기능 시스템과의 통합(A~D 단계)

A~D 단계에서는 기존 `capability_handler_registry.py`가 폐지되고 `function_registry.py`(`FunctionRegistry`)으로 통합되었습니다. 모든 기능(커널 핸들러, core_pack 기능, Pack 제공 기능)은 `FunctionRegistry`에 등록되어 있으며, `capability_executor.py`에서는 이를 일률적으로 실행한다.

#### 주요 변경 사항

`capability_handler_registry.py`이 삭제되었습니다. 대안으로 `core_runtime/function_registry.py`은 `FunctionRegistry` 및 `FunctionEntry` 데이터 클래스를 정의합니다. `ManifestRegistry`는 `FunctionRegistry`(설계 결정 D-6)의 별칭입니다.

#### FunctionEntry의 주요 필드

| 필드 | 유형 | 설명 |
|-----------|-----|------|
| `function_id` | `str` | 기능 ID |
| `pack_id` | `str` | 제휴 팩 ID |
| `qualified_name` | `str`(속성) | `{pack_id}:{function_id}`(콜론으로 구분) |
| `calling_convention` | `Optional[str]` | 실행 방법. 7종 중 임의 |
| `permission_id` | `Optional[str]` | 부여 ID(지원 유효성 검사에 사용됨) |
| `entrypoint` | `Optional[str]` | 진입점(예: `main.py:run`) |
| `risk` | `Optional[str]` | 위험 수준 |
| `is_builtin` | `bool` | 내장된 기능인가요? |
| `runtime` | `str` | `python` / `binary` / `command` |
| `handler_py_sha256` | `Optional[str]` | handler.py의 SHA-256(신뢰 확인용) |
| `vocab_aliases` | `Optional[List[str]]` | 어휘 별칭(`resolve_by_alias()`에서 검색 가능) |
| `grant_config` | `Optional[Dict]` | 부여 설정(None이 아닌 경우 부여 확인 수행) |

#### Calling_Convention (7종)

| 전화 컨벤션 | 설명 |
|-------------------|------|
| `kernel` | 커널 처리기로 직접 실행합니다. `capability_executor`을 통해 실행할 수 없습니다 |
| `subprocess` | 하위 프로세스에서 실행(진입점 지정) |
| `block` | core_pack의 DI 서비스를 통해 실행 |
| `python_host` | 호스트 Python에서 실행됩니다(`RUMI_ALLOW_HOST_EXECUTION=1` 필요) |
| `python_docker` | Docker 컨테이너에서 실행(기본값) |
| `binary` | 바이너리 직접 실행 |
| `command` | 명령 실행 |

#### 커널 기능

`kernel.py`은 `_KERNEL_HANDLER_MANIFESTS`을 정의합니다. 70개(시스템 29 + 런타임 41) 핸들러는 `register_kernel_function()`, `pack_id="kernel"`, `calling_convention="kernel"` 및 `FunctionRegistry`에 등록되어 있습니다.

#### 실행 흐름

```
capability_executor.execute(principal_id, request)
    ↓
FunctionRegistry で permission_id を解決（resolve_by_alias）
    ↓
_unified_execute(entry, principal_id, request)
    ↓
Trust チェック（sha256 検証）
    ↓
Grant チェック（grant_config が非 None のとき）
    ↓
calling_convention で分岐実行
```

---

## UDS 소켓 권한

### 문제

엄격 모드에서 Pack 실행 컨테이너는 `--user=65534:65534`(아무도 없음)으로 실행됩니다. UDS 소켓이 기본 `0660`(루트:루트)에 남아 있으면 컨테이너가 소켓에 연결할 수 없습니다.

### 솔루션

전용 GID를 설정하면 `0660`을 유지하면서 안전하게 연결할 수 있습니다.

| 환경 변수 | 설명 | 기본값 |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` | 송신 소켓 GID | 없음 |
| `RUMI_CAPABILITY_SOCKET_GID` | 기능 소켓 GID | 없음 |
| `RUMI_EGRESS_SOCKET_MODE` | 송신 소켓 권한 | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` | 기능 소켓 권한 | `0660` |

GID가 설정되면 `--group-add=<GID>`가 `docker run`에서 자동으로 부여됩니다.

이는 `RUMI_EGRESS_SOCKET_MODE=0666` / `RUMI_CAPABILITY_SOCKET_MODE=0666`을 사용하여 완화할 수 있지만 임의의 사용자가 소켓에 연결할 수 있도록 허용하므로 더 이상 사용되지 않습니다.

---

## 계층적 권한

### 개요

`pack_id`를 `parent__child`으로 변경하면 부모-자식 관계의 Pack을 표현할 수 있습니다. 자식은 허용되지만 부모는 허용되지 않는 경우 실행이 거부됩니다.

상위 구성은 하위 항목에 대한 상한(교차점)을 설정합니다. 하위 레벨만 허용하더라도 상위 레벨에서 허용하지 않으면 작동하지 않습니다.

---

## 비밀

API 키와 같은 비밀값을 안전하게 관리하세요.

- `.env` 사용하지 않음(사고율 감소)
- `user_data/secrets/`에 저장됩니다. (키 1개 = 파일 1개, 묘비, 일지)
- 로그에 비밀 값을 표시하지 않습니다(감사 및 진단 모두).
- 비밀 파일을 Pack에 직접 표시하지 마세요.
- 능력을 통해 획득(예: `secrets.get`)
- API는 목록(마스크 포함)/설정/삭제(재표시 없음)만 가능합니다.

---

## 공유 사전

### 개요

이는 `namespace` / `token`를 다시 작성할 수 있는 메커니즘입니다. 관계자는 네임스페이스의 의미를 해석하지 않습니다(생태계가 자유롭게 결정함).

### 안전 기능

- **주기 감지**: A→B→A와 같은 주기를 자동으로 거부합니다.
- **충돌 감지**: 동일한 토큰에 대해 다른 값을 등록하려는 시도는 거부됩니다.
- **홉 제한**: 기본 10홉 이후 해결 중단
- **감사 로그**: 모든 작업을 기록합니다.

### 지속성

`snapshot.json`(스냅샷)과 `journal.jsonl`(저널)은 `user_data/settings/shared_dict/`에 저장됩니다.

---

## lib 시스템

### 개요

팩 초기화 및 업데이트 처리를 관리합니다. 상주하지 않으며 필요할 때만 실행됩니다.

### 실행 타이밍

| 조건 | 실행할 파일 |
|------|-------------------|
| 첫 소개(기록 없음) | `lib/install.py` |
| 해시 변경 | `lib/update.py`(`install.py`이 아닌 경우) |
| 변화 없음 | 실행하지 마십시오 |

### 도커 격리

엄격 모드에서는 Docker 컨테이너 내에서 격리되어 실행됩니다. `--network=none`, `--cap-drop=ALL`, `--read-only`, `--memory=256m`. RW 마운트는 `user_data/packs/{pack_id}/`(컨테이너 내: `/data`)로만 제한됩니다.

---

## pip 종속 라이브러리 설치

### 개요

팩은 `requirements.lock`을 포함하여 PyPI 패키지에 대한 종속성을 선언할 수 있습니다. 사용자가 API를 통해 승인하면 빌더의 Docker 컨테이너에 안전하게 다운로드되어 설치됩니다. 호스트 Python 환경은 더럽지 않습니다.

### 요구사항.잠금 규칙

`NAME==VERSION` 라인만 허용됩니다(주석/빈 라인은 허용됩니다). 다음은 금지됩니다: `-e`(편집 가능), `git+` / `http://` / `https://`(URL/VCS 참조), `file:` / `../` / `/`(로컬 참조), `--` 선택적 행, `@` 직접 참조.

### 상태 전환

```
scan → pending → approve → installed
                → reject  → rejected (cooldown 1h)
                            → 3回 reject → blocked → unblock → pending
```

### 보안

휠 전용이 기본값입니다(`--only-binary=:all:`). sdist가 필요한 경우 승인 시 `allow_sdist: true`을 지정하세요. 빌더 컨테이너(다운로드)는 `--network=bridge` + `--cap-drop=ALL`에서 실행되고, 빌더 컨테이너(설치)는 `--network=none`(완전 오프라인)에서 실행됩니다. 실행 컨테이너에서 사이트 패키지는 읽기 전용(`/pip-packages:ro`)으로 마운트되고 `PYTHONPATH`에 추가됩니다.

### index_url 제약 조건

`https` 계획만 허용됩니다. 호스트 이름이 localhost / 127.0.0.1 / ::1 / 개인 IP / link-local인 경우 거부됩니다.

---

## 팩 가져오기/적용

### 가져오기

/ `.zip` / `.rumipack`(zip 호환) 폴더에서 팩을 스테이징으로 가져옵니다. "단일 최상위 디렉토리 필요" 및 zip 슬립/크기 제한과 같은 보호가 zip 구조에 적용됩니다.

### 신청

스테이징부터 생태계까지 적용됩니다. 백업이 자동으로 생성됩니다. 신청 시 `pack_id`와 `pack_identity`(`ecosystem.json`의 `pack_identity` 필드)을 모두 비교하여 기존 Pack과 불일치하는 경우 불합격 처리됩니다.

---

## 구성 요소 개념

### 개요

`backend_core/ecosystem/registry.py`는 `pack_subdir/components/*/manifest.json`을 읽고 `ComponentInfo`를 빌드합니다. 구성요소는 수명주기 관리(예: 설정)를 위한 단위입니다.

### python_file_call과의 관계

`python_file_call`에는 구성 요소를 특별하게 처리하고 자동으로 블록을 검색하는 기능이 없습니다. `components/{component_id}/blocks/`에 있는 파일을 실행하려면 `file` 필드에 상대 경로를 지정하세요.

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

---

## 어휘/변환기

> **참고**: 이 기능은 호환성 흡수를 위한 고급 기능입니다. 일반적인 Pack 개발에서는 사용할 필요가 없습니다.

### vocab.txt (동의어 그룹)

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

### 변환기 보안 점검

#### 문제

`ConverterASTChecker`는 변환기 스크립트의 AST 구문 분석을 수행하고 `blocked_imports`(`os`, `subprocess`, `socket` 등)의 사용을 감지하고 거부합니다. 그러나 현재 검사는 변환기 파일만 대상으로 합니다. 변환기가 `from .helper import func` 또는 `import local_module`와 같은 로컬 모듈을 가져오는 경우 가져온 파일에 차단된 가져오기가 포함되어 있어도 차단된 가져오기를 감지할 수 없습니다.

```
converter.py          ← 検査される（Level 0）
 └─ import helper     ← helper.py は検査されない
     └─ import os     ← blocked import が素通り
```

#### 검사 수준 정의

| 레벨 | 검사범위 | 장점 | 단점 | 구현 비용 |
|--------|---------|----------|-----------|-----------|
| 레벨 0(현재) | 단일 변환기 파일 | 구현이 빠르고 부작용이 없습니다 | 차단된 가져오기는 로컬 가져오기를 통해 우회 가능 | 없음 |
| 레벨 1(권장) | 변환기 + 동일한 디렉토리에서 `.py`의 재귀 순회 | 가장 일반적인 우회 패턴을 방지합니다. 간단한 구현 | 동일한 디렉토리 외부의 종속성은 검사되지 않습니다. | 낮음(약 50줄) |
| 레벨 2 | pack_subdir 전체에 걸쳐 가져오기 그래프의 재귀 순회 | 전체 종속성 트리를 검사할 수 있습니다 | 구현이 복잡합니다. 재귀 깊이 관리, 순환 감지 및 경로 해결을 고려해야 합니다. 성능 비용 포함 | 중간 ~ 높음(약 150줄) |

#### 권장: 레벨 1

다음 웨이브에서는 레벨 1을 구현하는 것이 좋습니다.

- 변환기의 로컬 종속성은 일반적으로 동일한 디렉터리에 배치됩니다(`converters/` 아래에 도우미를 배치하는 패턴).
- 동일한 디렉터리로 제한하면 경로 확인이 간단하고 오탐 위험이 낮습니다.
- 레벨 2에서는 변환기가 여러 디렉터리에 걸쳐 있도록 설계되었다고 가정하지만 현재 변환기 규칙에서는 이러한 경우가 거의 없습니다.

사용 사례가 확인되면 레벨 2가 고려됩니다.

#### 레벨 1 의사코드

```python
def check_converter_with_locals(
    converter_path: Path,
    blocked: set[str],
) -> list[str]:
    """converter と同一ディレクトリのローカル .py を再帰的に AST 検査する。"""
    violations: list[str] = []
    converter_dir = converter_path.parent
    visited: set[Path] = set()

    def _check(target: Path) -> None:
        if target in visited:
            return                          # 循環 import 防止
        visited.add(target)
        tree = ast.parse(target.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            # ast.Import      → [alias.name for alias in node.names]
            # ast.ImportFrom   → node.module（相対 import の場合 None あり）
            for name in _extract_module_names(node):
                if name in blocked:
                    violations.append(f"{target.name}: blocked import '{name}'")
                # 同一ディレクトリに .py があればローカル依存として再帰検査
                local = converter_dir / f"{name.split('.')[0]}.py"
                if local.exists() and local != target:
                    _check(local)

    _check(converter_path)
    return violations
```

> `_extract_module_names()`은 `ast.Import` / `ast.ImportFrom` 노드에서 모듈 이름 문자열 목록을 반환하는 도우미입니다. 기존 `ConverterASTChecker` 로직을 재사용할 수 있습니다.

#### 테스트 계획(레벨 1)

| # | 시나리오 | 예상되는 결과 |
|---|---------|---------|
| 1 | 변환기 단독 `import subprocess` | 거부 |
| 2 | 변환기 → `from .helper import x` → `helper.py`에서 `import os` | 거부(로컬 종속성을 통한 차단된 가져오기 감지) |
| 3 | 변환기 → `from .helper import x` → `helper.py`이 깨끗함 | 허용 |
| 4 | 변환기 → `import requests`(외부 패키지, 로컬로 `.py` 없음) | 허용(로컬 파일이 없어 건너뛰기) |
| 5 | 변환기 → `helper.py` → `from .utils import y` → `utils.py`에서 `import socket` | 거부(재귀 스캔으로 감지) |
| 6 | 순환 가져오기: 변환기 → 도우미 → 변환기 | 무한 루프 없이 정상적으로 종료됩니다(방문 세트로 인해 방지됨) |
| 7 | 변환기 디렉터리 외부로 가져오기(`from ..other import z`) | 건너뛰기(레벨 1 검사 범위 밖. 레벨 2에서 지원) |

---

## 감사 로그

### 개요

모든 중요한 작업은 JSON Lines 형식으로 `user_data/audit/`에 기록됩니다.

### 카테고리

| 카테고리 | 내용 |
|----------|------|
| `flow_execution` | 흐름 실행 |
| `modifier_application` | 수정자 적용 |
| `python_file_call` | 실행 차단 |
| `approval` | 팩 승인작업 |
| `permission` | 권한운영(네트워크 부여, 능력 부여 포함) |
| `network` | 네트워크 통신 |
| `security` | 보안 이벤트 |
| `system` | 시스템 이벤트(lib, pip, 보류 중인 내보내기 등) |

### 파일 이름 지정

`{category}_{YYYY-MM-DD}.jsonl`

파일 이름의 날짜는 항목의 `ts`(타임스탬프)에 따라 결정됩니다. 자정이 지나도 해당 항목의 `ts`에 해당하는 파일로 분류됩니다. `ts`가 유효하지 않은 경우 작성 당시 날짜로 되돌아갑니다.

### 항목 구조

```json
{
  "ts": "2024-01-01T00:00:00Z",
  "category": "python_file_call",
  "severity": "info",
  "action": "execute_python_file",
  "success": true,
  "flow_id": "ai_response",
  "step_id": "generate",
  "phase": "generate",
  "owner_pack": "ai_client",
  "execution_mode": "container",
  "details": {
    "file": "blocks/generate.py",
    "execution_time_ms": 150.5
  }
}
```

---

## 내보내기 보류 중

### 개요

`user_data/pending/summary.json`은 시작 시 자동으로 생성됩니다. 외부 도구는 이 파일을 읽는 것만으로도 승인 상태를 이해할 수 있습니다. 공무원은 이 파일의 소비자에게 특별한 대우를 제공하지 않습니다(편의 금지).

### 출력 형식

```json
{
  "ts": "2026-02-11T15:00:00Z",
  "version": "1.0",
  "packs": {
    "pending_count": 2,
    "pending_ids": ["pack_a", "pack_b"],
    "modified_count": 1,
    "modified_ids": ["pack_c"],
    "blocked_count": 0,
    "blocked_ids": []
  },
  "capability": {
    "pending_count": 1,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 3
  },
  "pip": {
    "pending_count": 0,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 2
  }
}
```

각 모듈을 가져올 수 없는 경우 해당 섹션에는 `"error"` 키(페일소프트)가 포함됩니다.

---

## DI 컨테이너 및 서비스 목록

### 개요

`backend_core/di_container.py`은 Rumi AI OS 전반에 걸쳐 사용되는 경량 DI(종속성 주입) 컨테이너입니다. 모든 서비스는 컨테이너에 등록되고 이름으로 검색됩니다. 전역 싱글톤으로 `get_container()`을 통해 액세스합니다.

### DIContainer 클래스

| 방법 | 설명 |
|---------|------|
| `register(name, factory)` | 팩토리 함수를 이름으로 등록합니다. 처음에 인스턴스화됨 `get`(지연 생성) |
| `get(name)` | 인스턴스를 얻으세요. 등록되지 않은 경우 `KeyError` |
| `get_or_none(name)` | 인스턴스를 얻으세요. 등록되지 않은 경우 `None` |
| `has(name)` | 등록 여부 확인 |
| `reset()` | 모든 등록 지우기 |
| `set_instance(name, instance)` | 기존 인스턴스 직접 등록(테스트용) |

### 글로벌 액세스

| 기능 | 설명 |
|------|------|
| `get_container()` | 글로벌 컨테이너 가져오기(싱글톤) |
| `reset_container()` | 전역 컨테이너 재설정(테스트용) |

### 등록된 서비스 목록(32개 서비스)

| 웨이브 | 서비스 이름 |
|------|-----------|
| 웨이브 1 | `audit_logger`, `hmac_key_manager` |
| 웨이브 2 | `vocab_registry`, `network_grant_manager`, `store_registry` |
| 웨이브 3 | `approval_manager`, `permission_manager` |
| 웨이브 4 | `container_orchestrator`, `host_privilege_manager`, `flow_composer`, `function_alias_registry`, `secrets_store`, `secrets_grant_manager`, `modifier_loader`, `modifier_applier` |
| 웨이브 5 | `pack_api_server`, `egress_proxy_manager`, `python_file_executor`, `secure_executor`, `lib_executor`, `unit_executor`, `capability_executor` |
| 웨이브 8 | `diagnostics`, `install_journal`, `interface_registry`, `event_bus`, `component_lifecycle` |
| 웨이브 15 | `health_checker`, `metrics_collector`, `profiler` |
| 웨이브 22 | `docker_capability_handler` |
| 웨이브 24 | `function_registry` |

---

## 커널 믹스인 구성

### 개요

`backend_core/kernel.py`은 4개의 Mixin 클래스를 구성하여 커널을 구성합니다. 단일 파일 팽창을 피하면서 관심에 따라 구현을 분리합니다.

### 믹스인 목록

| 믹스인 클래스 | 파일 | 책임 |
|-------------|---------|------|
| `KernelCore` | `kernel_core.py` | 엔진 본체. 흐름 로딩, 컨텍스트 구성, 종료 |
| `KernelFlowExecutionMixin` | `kernel_flow_execution.py` | 플로우 실행, `depends_on` 해결, 조건 평가 |
| `KernelSystemHandlersMixin` | `kernel_handlers_system.py` | 시작/시스템 핸들러(초기화, 스캔, 승인 등) |
| `KernelRuntimeHandlersMixin` | `kernel_handlers_runtime.py` | 연산/실행 핸들러(흐름 실행, 능력 호출 등) |

### 합성

```python
# kernel.py
class Kernel(
    KernelRuntimeHandlersMixin,
    KernelSystemHandlersMixin,
    KernelFlowExecutionMixin,
    KernelCore,
):
    pass
```

MRO(Method Resolution Order)는 Runtime → System → FlowExecution → Core의 순서로 해결됩니다. 각 믹스인은 `KernelCore`(`self.container`, `self.context` 등)의 속성에 따라 달라집니다.

---

## 관찰 가능성

### 개요

Wave 15에 추가된 4개의 모듈은 구조화된 로그, 상태 확인, 지표 및 프로파일링을 제공합니다.

### 구조적 로깅(logging_utils.py)

`backend_core/logging_utils.py`은 표준 `logging`을 래핑하고 구조화된 출력 및 컨텍스트 전파를 제공합니다.

| 클래스/기능 | 설명 |
|--------------|------|
| `StructuredFormatter` | JSON 또는 텍스트 형식으로 로그 형식 지정 |
| `StructuredLogger` | `logging.Logger` 래퍼. `bind()`에서 키-값 컨텍스트 제공 |
| `CorrelationContext` | 스레드로부터 안전한 `correlation_id` 관리. 요청별 추적에 사용 |
| `get_structured_logger(name)` | 캐시가 있는 공장. 동일한 이름으로 호출하면 동일한 인스턴스가 반환됩니다. |
| `configure_logging()` | 글로벌 로그 설정(레벨, 포맷)을 한번에 적용 |

환경 변수 `RUMI_LOG_LEVEL`(기본값 `INFO`) 및 `RUMI_LOG_FORMAT`(`json` 또는 `text`, 기본값 `text`)이 동작을 제어합니다.

### 상태 확인(health.py)

`backend_core/health.py`은 프로브 기반 상태 확인 메커니즘을 제공합니다. `app.py --health`에서 사용됩니다.

| 클래스/기능 | 설명 |
|--------------|------|
| `HealthChecker` | 프로브 등록, 시간 초과와 병렬로 실행 및 결과 집계 |
| `HealthStatus` | `UP` / `DOWN` / `DEGRADED` / `UNKNOWN`의 4가지 상태 |
| `probe_disk_space` | 여유 디스크 공간 확인(내장 프로브) |
| `probe_memory` | 메모리 사용량 검사(내장 프로브) |
| `probe_file_writable` | 파일을 쓸 수 있는지 확인(내장 프로브) |

모든 프로브가 `UP`이면 모든 프로브도 `UP`로 판정되고, 그 중 하나라도 `DOWN`이면 `DEGRADED`로 판정되며, 모든 프로브가 `DOWN`이면 `DOWN`로 판정된다.

### 측정항목(metrics.py)

`backend_core/metrics.py`은 애플리케이션 측정항목 수집을 위한 기반을 제공합니다.

| 방법 | 설명 |
|---------|------|
| `increment(name, labels, value)` | 증가 카운터 |
| `set_gauge(name, labels, value)` | 게이지 설정 |
| `observe(name, labels, value)` | 히스토그램에 값 기록 |
| `timer(name, labels)` | 컨텍스트 관리자. 블록 실행 시간 자동 기록 |
| `snapshot()` | 사전에 있는 모든 측정항목의 현재 값을 반환합니다. |

라벨(사전)을 사용하면 측정항목을 여러 측정기준으로 분류할 수 있습니다. Wave 15에서는 `kernel_flow_execution.py`(단계 실행 시간), `kernel_handlers_system.py` / `kernel_handlers_runtime.py`(핸들러 호출 횟수/시간)에 통합되었습니다.

### 프로파일링(profiling.py)

`backend_core/profiling.py`은 함수 및 블록에 대한 실행 시간 프로파일링을 제공합니다.

| 메소드/데코레이터 | 설명 |
|--------------------|------|
| `profile(name)` | 컨텍스트 관리자. 블록 실행 시간 기록 |
| `profile_func(name)` | 동기 함수용 데코레이터 |
| `profile_async(name)` | 비동기 함수용 데코레이터 |
| `summary()` | p50/p95/p99 백분위수로 요약 반환 |

`max_samples`을 메모리 제한으로 설정할 수 있으며, 제한이 초과되면 오래된 샘플이 삭제됩니다. Wave 15에서는 `kernel_flow_execution.py`(Flow 실행 시간, Step 실행 시간)에 통합되었습니다.

---

## 공통 기본 모듈

### 개요

패키지 전체에서 공유되는 Wave 12~15에 추가된 유틸리티 세트입니다.

### 공통 유효성 검사(validation.py)

`backend_core/validation.py`은 Pack / Flow / Modifier(Wave 12 추가)에 대한 검증 유틸리티를 제공합니다. 스키마 유효성 검사, 필수 필드 유효성 검사, 값 범위 유효성 검사 등의 공통 논리를 중앙 집중화하여 각 모듈에서 중복을 제거합니다.

### 통합 오류 시스템(error_messages.py)

`backend_core/error_messages.py`은 Rumi AI OS 전체에 걸쳐 통합된 오류 코드 시스템을 정의합니다.

| 요소 | 설명 |
|------|------|
| `ErrorCode` | 고정된 데이터 클래스. `RUMI-{CAT}-{NNN}` 형식(예: `RUMI-AUTH-001`) |
| 카테고리 | `AUTH`(인증), `NET`(네트워크), `FLOW`(플로우), `PACK`(팩), `CAP`(기능), `VAL`(검증), `SYS`(시스템) |
| `RumiError` | 균일한 예외 클래스. `code`, `message`, `details`, `suggestion` 유지 |
| `format_error()` | 템플릿 확장 도우미. 메시지의 자리 표시자를 동적으로 채우기 |

에러코드는 자동수집 레지스트리에서 관리되며, 모듈이 로딩되면 자동으로 레지스트리에 등록됩니다.

### 유형 정의(types.py + py.typed)

`backend_core/types.py`은 패키지 전체에서 사용되는 유형 정의를 집계합니다.

| 유형 | 정의 |
|------|------|
| 뉴타입 | `PackId`, `FlowId`, `CapabilityName`, `HandlerKey`, `StoreKey` |
| 별칭 입력 | `JsonValue`, `JsonDict` |
| 일반 | `Result[T]`(성공 값 또는 오류 유지) |
| 열거형 | `Severity`（`info`, `warn`, `error`, `critical`） |

`py.typed` 마커 파일(PEP 561)이 포함되어 외부 도구(mypy 등)를 사용하여 유형을 확인할 수 있습니다.

### 지원 중단 관리(deprecation.py)

`backend_core/deprecation.py`은 더 이상 사용되지 않는 API에 대한 관리 및 경고를 제공합니다.

| 요소 | 설명 |
|------|------|
| `DeprecationInfo` | 고정된 데이터 클래스. 더 이상 사용되지 않는 대상, 버전 및 대안 보존 |
| `DeprecationRegistry` | 하나씩 일어나는 것. 스레드로부터 안전하게 지원 중단 정보 관리 |
| `deprecated()` | 함수/메서드용 데코레이터(비동기 호환) 호출 시 경고 출력 |
| `deprecated_class()` | 수업을 위한 데코레이터. 인스턴스 생성 시 경고 출력 |

환경 변수 `RUMI_DEPRECATION_LEVEL`는 동작을 제어합니다: `warn`(기본값, 경고 인쇄), `error`(예외 발생), `silent`(무시), `log`(로그만).

---

## 팩 개발 도구

### 개요

`backend_core/pack_scaffold.py`은 팩 템플릿을 생성하는 CLI 도구입니다.

### PackScaffold 클래스

네 가지 유형의 템플릿에서 Pack 디렉터리 구조와 파일을 자동으로 생성합니다.

| 템플릿 | 설명 |
|------------|------|
| `minimal` | 최소한의 구성. `ecosystem.json` + 비어 있음 `backend/`만 |
| `capability` | 기능 처리기를 사용합니다. `share/capability_handlers/` 포함 |
| `flow` | 흐름과 함께. `backend/flows/` 및 `backend/blocks/` 포함 |
| `full` | 모든 요소를 ​​포함한 풀 세트입니다. `lib/`, `converters/`, `modifiers/` 등을 포함 |

생성된 파일은 잘못된 구조를 방지하기 위해 `validation.py`로 검증됩니다.

### CLI 진입점

```bash
python -m backend_core.pack_scaffold --template full --pack-id my_pack --output ecosystem/my_pack
```

`--template`(템플릿 이름), `--pack-id`(팩 ID) 및 `--output`(출력 경로)를 지정합니다.

---

## 더 이상 사용되지 않는 기능

### 생태계/흐름/(local_pack)

`ecosystem/flows/`에 직접 배치된 Flow/Modifier를 가상 팩으로 처리하는 호환 모드입니다. 기본적으로 비활성화되어 있습니다(`RUMI_LOCAL_PACK_MODE=off`). `RUMI_LOCAL_PACK_MODE=require_approval`로 활성화할 수 있지만 권장되지 않습니다.

지원 중단 일정: v2.0에서는 경고와 함께 호환성 모드가 유지되었으며 v3.0에서는 제거될 예정입니다.

이동 대상 : 팩으로 만들어 `ecosystem/<pack_id>/backend/`에 넣거나 `user_data/shared/flows/`에 넣습니다.

### addon_manager

JSON 패치 기반 애드온 메커니즘은 `backend_core/ecosystem/addon_manager.py`에 존재했지만 2단계에서 제거되었습니다. 현재 코드베이스에는 존재하지 않습니다.

### 흐름/디렉토리

이전 `flow/` 디렉토리는 더 이상 사용되지 않습니다. 팩으로 `flows/`, `user_data/shared/flows/`, `flows/`로 이동해주세요.

### 삭제된 파일

다음 파일/디렉토리가 삭제되었습니다.

| 삭제 대상 | 교체 | 이유 |
|---------|------|------|
| `capability_handler_registry.py` | `function_registry.py` | FunctionRegistry에 통합(A~D 단계) |
| `builtin_capability_handlers/` | `core_pack/` | core_pack으로 마이그레이션 |

# Defaultspack 함수 경계

Defaultspack은 이제 함수 매니페스트를 공개 작업 경계로 처리합니다. HTTP 경로는 호환성 어댑터이고, AI 도구는 선택적 외관이며, Flow/function.call 호출은 모두 도메인 서비스에 도달하기 전에 동일한 defaultspack 함수에 수렴됩니다.
