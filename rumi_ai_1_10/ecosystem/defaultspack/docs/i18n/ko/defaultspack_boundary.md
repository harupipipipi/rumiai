<!-- docs-i18n-links:start -->
[EN](../../defaultspack_boundary.md) | [JP](../ja/defaultspack_boundary.md) | [KR](./defaultspack_boundary.md) | [CN](../zh-cn/defaultspack_boundary.md)
<!-- docs-i18n-links:end -->

# Defaultspack 경계

defaultspack은 Rumi의 핵심 런타임 팩입니다. 공통 실행을 제공합니다.
팩과 사용자 데이터를 위한 표면이지만 구체적인 도구 모음은 아닙니다.
에이전트 제품, 프롬프트, UI 항목 또는 모델 카탈로그.

## Defaultspack에 속함

- 런타임, 브로커, 레지스트리 로더, 어댑터 및 전송 코드.
- 기능 계약, 스키마 어휘 및 일반 실행 브리지.
- 도구, 프롬프트, 프로필, 사전 설정, UI 매니페스트를 위한 Pack/user_data 로더
  공급자 카탈로그 및 기능.
- 모듈 목록, 팩 요청, 정책 등 핵심 관리 기능
  검토.
- 런타임을 연결하는 데 필요한 최소한의 시작 그래프.

## 팩 또는 사용자 데이터에 속함

- AI 관련 도구 정의 및 구체적인 도구 구현.
- 상담원 행동 프롬프트, 프로필, 사전 설정, 예시 및 제품별
  그래프.
- 운영 회사 등 제품 프로필.
- 사이드바 항목, 설정 섹션, 렌더러, 앱 셸 변형 및 기타
  구체적인 프론트엔드 선언.
- 공급자 및 모델 카탈로그 데이터.

## 스타터 팩

기본 로컬 환경은 defaultspack과 스타터 팩으로 구성됩니다.

- `rumi_default_tools_pack`: 기본 도구 매니페스트 및 도구 기능.
- `rumi_local_agent_pack`: 로컬 에이전트 프롬프트, 프로필, 사전 설정 및 예시.
- `rumi_operations_company_pack`: 운영 회사 프로필, 그래프, 경로 및 UI.
- `rumi_reference_ui_pack`: 사이드바 및 패널 매니페스트를 참조합니다.
- `rumi_model_catalog_pack`: 공급자/모델 카탈로그 매니페스트 및 공급자 UI.

로더는 설치된 팩과 `user_data`을 모아서 연결해야 합니다.
가능하다면 `source_pack_id`. defaultspack은 더 이상 사용되지 않는 호환성을 유지할 수 있습니다
별칭이지만 새로운 구체적인 콘텐츠는 팩이나 사용자 데이터에 포함되어야 합니다.
