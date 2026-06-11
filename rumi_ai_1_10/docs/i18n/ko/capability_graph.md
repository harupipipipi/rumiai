<!-- docs-i18n-links:start -->
[EN](../../capability_graph.md) | [JP](../ja/capability_graph.md) | [KR](./capability_graph.md) | [CN](../zh-cn/capability_graph.md)
<!-- docs-i18n-links:end -->

# 능력 그래프

기능 그래프는 기존 실행 흐름 시스템 옆에 있는 기능 연결 계층입니다.

실행 흐름은 시작, 설정, 핸들러 실행, 하위 흐름, 함수 호출, `python_file_call`, `universal_call`, 스케줄러 통합 및 명시적 파이프라인 등 순서가 지정된 런타임 절차를 계속 담당합니다.

Capability Graph는 AI 클라이언트, 에이전트, 도구 번들, 메모리, 프롬프트, 자격 증명, 정책, 프런트엔드 표면, CLI 표면 및 향후 팩 정의 기능 등 어떤 런타임 기능이 연결될 수 있는지 선언하는 역할을 담당합니다.

## 핵심 경계

코어는 도메인 중립을 유지해야 합니다. 다음과 같은 일반적인 개념만 이해할 수 있습니다.

- 노드
- 항구
- 표준
- 가장자리
- 그래프
- 프로필
- 바인딩 핸들러 ID
- 검증 결과
- 진단

핵심은 `agent`, `tool`, `ai_client`, `frontend`, `cli`, `memory` 또는 `prompt`와 같은 도메인 의미로 분기되어서는 안 됩니다. 도메인별 연결 동작은 에코시스템 팩 바인딩 처리기에 속합니다.

허용되는 핵심 동작:

- 엣지 호환성 검증
- 승인된 바인딩 처리기를 해결합니다.
- 해당 바인딩 핸들러를 호출합니다.
- 진단 기록
- `InterfaceRegistry`에 그래프/프로필/런타임 프로필 값을 등록합니다.

금지된 핵심 동작:

```python
if target_node.kind == "agent" and source_node.kind == "tool":
    profile["agents"][target]["tools"].append(source)
```

## 파일

기능 그래프 파일은 `.graph.yaml`을 사용합니다.

초기 발견 후보:

1. `user_data/shared/graphs/*.graph.yaml`
2. `ecosystem/<pack_id>/graphs/*.graph.yaml`
3. `graphs/*.graph.yaml`

중복된 `graph_id` 값이 발견되면 1단계에서는 이를 진단 오류로 처리합니다.

팩 제공 그래프 파일은 팩 제공 흐름 로딩과 동일한 신뢰 경계를 따라 기존 팩 승인 및 해시 확인 흐름을 통과한 팩에서만 로드됩니다. 사용자 공유 그래프 파일은 사용자 소유 구성으로 허용되지만 등록 또는 컴파일하기 전에 여전히 스키마 유효성 검사 및 진단이 필요합니다.

## 스키마

버전: `rumi.graph.v1`

```yaml
graph_id: coding_workspace
version: rumi.graph.v1
display_name:
  en: Coding Workspace
  ja: コーディングワークスペース
nodes:
  - id: start
    ref: rumi.start
  - id: agent
    ref: defaultspack.agent
edges:
  - id: start_to_agent
    from: start.out
    to: agent.start
    kind: binding
```

`nodes[].id`은 그래프 로컬 인스턴스 ID입니다. `nodes[].ref`은 노드 정의 ID를 가리킵니다. 동일한 노드 정의가 하나의 그래프에서 여러 번 인스턴스화될 수 있습니다.

끝점 형식:

```text
<graph_node_instance_id>.<port_id>
```

1단계 가장자리 종류:

- `binding`

예약된 미래 엣지 종류:

- `data`
- `event`
- `control`

알 수 없는 가장자리 종류는 1단계의 오류입니다.

## 검증

그래프 유효성 검사:

- 그래프 스키마가 유효합니다.
- 모든 노드 참조는 전역 노드 레지스트리에 존재합니다.
- 프로필 인식 유효성 검사가 요청되면 선택한 프로필에 의해 모든 노드 참조가 활성화됩니다.
- 모든 에지 엔드포인트가 올바르게 구문 분석됩니다.
- 참조된 포트가 모두 존재함
- 소스 포트는 `output`입니다.
- 대상 포트는 `input`입니다.
- 소스 표준과 대상 표준이 교차합니다.
- `multiple: false` 입력 포트에는 최대 하나의 수신 에지가 있습니다.
- `required: true` 입력 포트에는 수신 에지가 있습니다.

1단계 필수 포트 실패는 유효성 검사 오류입니다. 향후 초안 모드에서는 경고로 다운그레이드될 수 있습니다.

## 컴파일

그래프 컴파일은 첫 번째 구현부터 프로필을 인식해야 합니다.

입력:

```json
{
  "graph_id": "coding_workspace",
  "profile_id": "coding"
}
```

컴파일러의 책임:

- 그래프 및 프로필 로드
- 선택한 프로필을 사용하여 그래프 유효성을 검사합니다.
- 노드 정의 해결
- 승인된 바인딩 핸들러를 호출합니다.
- 런타임 프로필 사전 생성
- 프런트엔드/표면 바인딩 시 `runtime_profile.launch.surface` 파생
  발사 가능한 표면 노드를 가리킨다
- `InterfaceRegistry`에 `runtime_profile.<profile_id>.<graph_id>` 등록
- 진단 반환

컴파일러가 아닌 목표:

- 뷰어 UI 없음
- 핵심 컴파일러에는 공급자별 도구 스키마 변환이 없습니다.
- 코어에서 도메인별 `agent/tool/ai_client` 분기가 없습니다.

## 인터페이스 레지스트리 키

공정 능력 그래프 관련 객체는 다음 키 형태를 사용하여 등록됩니다.

```text
node.<node_id>
graph.<graph_id>
profile.<profile_id>
runtime_profile.<profile_id>.<graph_id>
```

## 코어 노드

`rumi.start`은 코어가 소유한 유일한 특수 노드입니다. Core는 생태계 노드 검색 전에 이를 등록합니다.

`rumi.start`에는 하나의 출력 포트가 있습니다.

```json
{
  "id": "out",
  "direction": "output",
  "standards": ["rumi.flow.start"],
  "multiple": true,
  "required": false
}
```

다른 모든 노드는 승인된 에코시스템 팩에서 검색됩니다. 에코시스템 팩은 코어 소유 내장 노드 ID를 재정의해서는 안 됩니다.

## 백엔드 API

백엔드는 인증된 HTTP API를 통해 기능 그래프 데이터를 노출합니다. `/api/*` 경로는 사양 지향 API 표면입니다. `/api/panel/*` 별칭은 제어판 세션 및 CSRF 흐름에 대해 동일한 모양을 반환합니다.

API 읽기:

- `GET /api/nodes`
- `GET /api/nodes/{node_id}`
- `GET /api/profiles`
- `GET /api/profiles/{profile_id}`
- `GET /api/profiles/{profile_id}/nodes`
- `GET /api/graphs`
- `GET /api/graphs/{graph_id}`

그래프 미리보기 API:

- `POST /api/graphs/{graph_id}/validate`
- `POST /api/graphs/{graph_id}/compile`

뷰어 측 노드 응답에는 프로필 선택 시 로케일 확인 레이블, 포트, 표준, 별칭, 바인딩, 메타데이터, 요구 사항, 권한 및 프로필 노드 상태가 포함됩니다. 프로필 노드 API는 설치되어 프로필이 활성화된 노드만 포함하는 `palette_nodes`도 반환하므로 뷰어는 노드 유형을 하드코딩할 필요가 없습니다.

컴파일 끝점은 기본적으로 패널 별칭의 미리 보기입니다. 호출자는 시작 시간 시작 프로필 정보 소스를 바꾸지 않고도 컴파일할 수 있습니다.

런타임 프로필이 실행될 때 컴파일 응답에는 `surface_launch_target`이 포함됩니다.
실행 가능한 프런트엔드 표면이 포함되어 있습니다. 이는 사용된 것과 동일한 표준 페이로드입니다.
시작 프로필 재시작 핸드오프를 통해:

```json
{
  "kind": "desktop_app",
  "pack_id": "frontendpack",
  "principal_id": "frontendpack",
  "surface": "browser",
  "node_instance_id": "frontendpack_web_surface",
  "node_id": "frontendpack.web_surface",
  "component_full_id": "frontendpack:frontend:web",
  "source": "capability_graph"
}
```

## 뷰어 노드 관리자

초기 Node Manager는 그래프 편집기 대체가 아닌 프로필 범위 카탈로그입니다. 다음이 표시됩니다.

- 능력 그래프 프로필
- 프로필 지원 팔레트 노드
- 설치됨, 비활성화됨, 누락됨, 승인되지 않음 및 누락된 구성 상태
- 노드 포트, 표준, 별칭, 바인딩 및 메타데이터
- 그래프 검증 및 미리보기 결과 컴파일

프로필 복제 컨트롤은 선택한 기능 그래프 프로필에 `permissions.can_create_profile: true`이 있는 경우에만 표시됩니다. 이 권한은 여전히 ​​사전 설정/UI 게이트입니다. 권한 있는 쓰기는 기존의 인증된 패널 API 및 파일 시스템 제어 뒤에 남아 있습니다.
