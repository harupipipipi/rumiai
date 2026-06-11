<!-- docs-i18n-links:start -->
[EN](../../capability_graph_pr_plan.md) | [JP](../ja/capability_graph_pr_plan.md) | [KR](./capability_graph_pr_plan.md) | [CN](../zh-cn/capability_graph_pr_plan.md)
<!-- docs-i18n-links:end -->

# 역량 그래프 홍보 계획

이 로드맵은 기능 그래프 작업을 검토 가능하게 유지합니다. 각 PR은 작아야 하며 기존 `.flow.yaml` 동작을 유지해야 하며 백엔드 기반이 안정될 때까지 뷰어 UI를 사용하지 않아야 합니다.

## PR 0: 문서 및 사양

범위:

- `docs/capability_graph.md`
- `docs/node_spec.md`
- `docs/profile_spec.md`
- `docs/port_standards.md`
- `docs/capability_graph_pr_plan.md`

수락:

- 문서만
- 런타임 구현 없음
- 뷰어 UI 없음
- 기존 테스트는 영향을 받지 않아야 합니다.

## PR 1: NodeDefinition 및 NodeDiscovery

범위:

- `core_runtime/node_models.py`
- `core_runtime/ecosystem_nodes.py`
- `kernel:node.load_all`
- `kernel:node.list`
- `kernel:node.get`
- 최소 기본 팩 `node.json`
- 테스트

필수 동작:

- 생태계 노드 발견 전에 핵심 소유 `rumi.start` 등록
- 출력 포트 `out` 및 표준 `rumi.flow.start`로 `rumi.start`을 정의합니다.
- 에코시스템 팩이 코어 소유 내장 노드 ID를 재정의하는 것을 방지합니다.
- 기존 승인 및 해시 검증을 통과한 팩에서만 팩에서 제공하는 노드 파일을 로드합니다.
- `rumi.node.v1` 구문 분석
- `contract`를 `standards`로 정규화합니다.
- `name`를 `display_name.en`로 정규화합니다.
- 중복 `node_id` 감지
- 잘못된 포트 방향 감지
- 유효하지 않은 표준 감지
- `InterfaceRegistry`에 `node.<node_id>` 등록

골이 아닌 경우:

- 그래프 로더
- 그래프 컴파일러
- 뷰어 UI

## PR 2: 프로필 로더 및 프로필 인식 노드 레지스트리

범위:

- `core_runtime/profile_models.py`
- `core_runtime/profile_loader.py`
- `core_runtime/profile_node_registry.py`
- `core_runtime/node_state.py`
- `kernel:profile.load_all`
- `kernel:profile.list`
- `kernel:profile.get`
- `kernel:profile.node_state`
- 샘플 프로필
- 테스트

필수 동작:

- 로드 `*.profile.yaml`
- 기존 승인 및 해시 검증을 통과한 팩에서만 팩 제공 프로필 파일을 로드합니다.
- `enabled_nodes` 및 `disabled_nodes` 구문 분석
- 보안 정보 소스로 만들지 않고 프로필 권한을 구문 분석합니다.
- 로케일 구문 분석 및 `node_settings`
- 프로필 노드 상태 계산
- `InterfaceRegistry`에 `profile.<profile_id>` 등록
- `StartupProfileManager`과 공존하여 적응합니다. PR 2는 시작 시간 시작 프로필을 연결하거나 대체하지 않습니다.

골이 아닌 경우:

- 그래프 컴파일러
- 뷰어 UI
- 기존 시작 프로필 모델을 대체합니다.

## PR 3: GraphLoader 및 PortStandardsValidator

범위:

- `core_runtime/graph_models.py`
- `core_runtime/capability_graph_loader.py`
- `core_runtime/port_standards.py`
- `kernel:graph.load_all`
- `kernel:graph.get`
- `kernel:graph.validate`
- `.graph.yaml` 설비
- 테스트

필수 동작:

- 로드 `.graph.yaml`
- 기존 승인 및 해시 검증을 통과한 팩에서만 팩에서 제공하는 그래프 파일을 로드합니다.
- 그래프 스키마 검증
- 노드 참조 확인
- 프로필 인식 노드 가용성 확인
- 엔드포인트 구문 분석
- 누락된 포트 감지
- 소스 및 타겟 방향 검증
- 표준 교차점 검증
- 입력 포트에 `multiple: false` 적용
- 필수 입력 포트 시행

골이 아닌 경우:

- 컴파일
- 바인딩 핸들러 실행

## PR 4: AgentEngine 도구 삽입 최소화

범위:

- AgentEngine AI 완성에 실행 도구 전달
- 승인/거부 루프를 통해 도구 유지
- 그래프 적용을 위한 기초로서 연결되지 않은 도구 호출을 거부합니다.
- 테스트

골이 아닌 경우:

- 그래프 컴파일러
- 전체 공급자별 스키마 어댑터

## PR 5: GraphCompiler 및 BindingHandlerResolver

범위:

- `core_runtime/capability_graph_compiler.py`
- `core_runtime/binding_handlers.py`
- `kernel:graph.compile`
- 테스트

필수 동작:

- 프로필 인식 컴파일
- 컴파일하기 전에 유효성을 검사합니다.
- 안전한 바인딩 핸들러 해결
- 직접 임의 수입이 없습니다.
- 런타임 프로필 dict 반환
- `InterfaceRegistry`에 `runtime_profile.<profile_id>.<graph_id>` 등록
- 진단 반환
- 컴파일러 코어에 AI/도구/에이전트별 분기 논리가 없는 회귀 테스트

## PR 6: defaultspack 노드 및 최소 바인딩

범위:

- defaultspack 에이전트, AI 클라이언트, 도구, 프런트엔드 노드 정의
- defaultspack 바인딩 핸들러
- 바인딩 핸들러 등록
- 샘플 그래프
- 테스트

필수 동작:

- `tool -> agent.tools`은 팩 바인딩을 통해 런타임 프로필에 도구 ID를 추가합니다.
- `ai_client -> agent.ai`는 팩 바인딩을 통해 AI 클라이언트 참조를 추가합니다.
- `cli surface -> frontend.surface`는 팩 바인딩을 통해 프런트엔드 표면 참조를 추가합니다.

## PR 7: 흐름은 명시적 그래프 컴파일 단계를 사용합니다.

범위:

- 명시적 단계로 `kernel:graph.compile`를 호출하는 고정물 흐름
- 테스트

필수 동작:

- 흐름 단계에서는 그래프 컴파일을 호출할 수 있습니다.
- 컴파일된 런타임 프로필은 출력 키를 통해 사용할 수 있습니다.
- 그래프 컴파일이 없는 흐름은 변경되지 않고 유지됩니다.

논골:

- `FlowDefinition`의 자동 `capability_graph` 필드

## PR 8: 연결된 도구 적용 및 스키마 어댑터

범위:

- defaultspack 도구 스키마 어댑터
- 그래프/프로필/주요 컨텍스트를 도구 실행에 전달
- 연결된 도구 시행
- `max_tool_calls` 등 프로필 정책의 기반 마련

## PR 9: 백엔드 API 통합

범위:

- 프로필 API
- 그래프 API
- 프로필 노드 상태 API
- 기능 그래프 프로필과 기존 시작 프로필 간의 관계를 문서화하고 노출합니다.

필수 동작:

- `StartupProfileManager`를 실행 시 정보 소스로 유지
- 기능 그래프 프로필을 그래프/런타임 사전 설정으로 노출
- 두 시스템 사이에 명시적인 API 브리지를 선택합니다.
- 기존 시작 프로필 모델을 자동으로 대체하지 마세요.
- 테스트

구현된 API 표면:

- `GET /api/nodes` 및 `GET /api/nodes/{node_id}`
- `GET /api/profiles` 및 `GET /api/profiles/{profile_id}`
- `GET /api/profiles/{profile_id}/nodes`
- `GET /api/graphs` 및 `GET /api/graphs/{graph_id}`
- `POST /api/graphs/{graph_id}/validate`
- `POST /api/graphs/{graph_id}/compile`
- 제어판 뷰어 세션의 `/api/panel/*` 별칭

프로필 API는 `StartupProfileManager`이 실행 시 정보 소스로 남아 있음을 나타내는 시작 프로필 관계 개체를 반환합니다. 기능 그래프 프로필은 시작 프로필을 자동으로 대체하는 것이 아니라 그래프/런타임 사전 설정 및 팔레트 필터로 노출됩니다.

## PR 10: 뷰어 노드 관리자

범위:

- 프로필 전환 UI
- 프로필 범위 노드 팔레트
- 디스플레이 활성화/비활성화
- 권한이 허용되는 경우에만 프로필 생성/복제 UI

구현된 뷰어 화면:

- `/panel/nodes` 노드 관리자 루트
- 프로필 전환기
- 프로필 범위 노드 카탈로그 및 팔레트 수
- 활성화, 비활성화, 준비, 구성 누락, 노드 누락 및 승인되지 않은 상태 표시
- 노드 포트, 표준, 바인딩 및 메타데이터 세부정보
- 그래프 검증 및 컴파일 미리보기 컨트롤
- `permissions.can_create_profile`이 true인 경우에만 프로필 복제 작업이 표시됩니다.

## 모든 PR을 위한 가드레일

- `.flow.yaml` 동작을 호환되게 유지하세요.
- 코어에 도메인 의미를 추가하지 마세요.
- 표준 포트 호환성 필드로 `standards`를 사용합니다.
- `contract` 및 `name`는 로더 호환성으로만 유지하세요.
- defaults/defaultspack 책임을 명시적으로 유지하세요.
- 로더, 유효성 검사기 및 컴파일러의 진단을 반환합니다.
- 노드, 프로필, 그래프, 컴파일러, AgentEngine 및 뷰어 작업을 하나의 PR에 결합하지 마십시오.
