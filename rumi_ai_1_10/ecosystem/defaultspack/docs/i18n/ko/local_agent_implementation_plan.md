<!-- docs-i18n-links:start -->
[EN](../../local_agent_implementation_plan.md) | [JP](../ja/local_agent_implementation_plan.md) | [KR](./local_agent_implementation_plan.md) | [CN](../zh-cn/local_agent_implementation_plan.md)
<!-- docs-i18n-links:end -->

# 현지 에이전트 구현 계획

## P0

- 기능 카탈로그: `capabilities/*.capability.yaml`를 로드하고 `/api/capabilities`을 노출합니다.
- 로컬 에이전트 프로필: `profiles/local_agent.profile.yaml`을 로드하고 `/api/agent-service/manifest`에 노출합니다.
- 계획 및 단계: `schemas/agent_plan.schema.yaml`, `schemas/agent_step.schema.yaml`, `blocks.agent.plan`를 사용하세요.
- 파일 작업 공간: 모든 작업을 작업 공간 루트 내부에 유지합니다. 읽기, 쓰기, 생성, 삭제, 목록, 검색, 비교, 스냅샷, 복원을 노출합니다.
- 터미널 및 git: 위험을 분류하고 실행을 위한 승인 필드를 요구하며 시도된 작업을 감사합니다.
- 안전: 기본 네트워크 거부, 비밀 수정 및 감사 메타데이터 기록.

## P1

- 메모리 및 프로젝트 컨텍스트: 검토 및 삭제 작업이 포함된 로컬 JSON/파일 저장소.
- 컴팩트: 롤링 요약, 고정된 컨텍스트 및 복원 메모.
- 아티팩트: 메타데이터를 사용하여 로컬 markdown/text/code/json/yaml/html/csv 아티팩트를 생성합니다.

## P2

- 조사: 먼저 로컬 소스를 검색하고 선택적으로 웹/브라우저 제공업체를 나중에 검색합니다.
- UI: 계획, 도구 호출, 파일 트리, 차이점, 터미널, 아티팩트, 메모리 및 승인을 위한 패널.

## 테스트

- 카탈로그 파일 로딩을 검증합니다.
- 대체 HTTP 레지스트리에 경로가 있는지 확인합니다.
- 프로필 및 기능 정책 메타데이터를 확인합니다.
- 위험한 작업에 대한 작업 공간 안전 및 승인 메타데이터를 확인합니다.
