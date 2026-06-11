<!-- docs-i18n-links:start -->
[EN](../../index.md) | [JP](../ja/index.md) | [KR](./index.md) | [CN](../zh-cn/index.md)
<!-- docs-i18n-links:end -->

# defaultspack 문서 색인

defaultspack 문서를 탐색할 때 여기에서 시작하세요. 정식 구현은 다음과 같습니다.
`rumi_ai_1_10/ecosystem/defaultspack/`.

이 섹션의 용어는 의도된 것입니다.

- `rule`: 범위 내의 상시 실행 명령 계층
- `skill`: 트리거 기반 또는 주문형 지침 및 작업 흐름 번들
- `prompt`: 런타임에 조합된 소스 자산 또는 렌더링된 모델 텍스트
- `system prompt`: 시스템 역할 프롬프트 텍스트에 대한 하위 수준 API/런타임 용어
- `delegation`: 다른 에이전트에게 작업을 보내는 정식 조치
- `team workspace`: 회사 조정 화면의 사용자 표시 이름입니다.
  내부 ID와 경로는 호환성을 위해 여전히 `company`로 표시될 수 있습니다.

리포지토리 전체 용어집 및 마이그레이션 지침은 다음을 참조하세요.
[`../../../docs/terminology.md`](../../../docs/terminology.md).

## 오리엔테이션

| 주제 | 문서 |
|---|---|
| PR97 아키텍처 개요 | [defaultspack-explained.md](defaultspack-explained.md) |
| 시작하기 | [getting-started.md](getting-started.md) |
| 런타임 아키텍처 | [architecture.md](architecture.md) |
| 지역 우선 정책 | [local_first_policy.md](local_first_policy.md) |
| 안전 및 허가 감사 | [safety_permission_audit_design.md](safety_permission_audit_design.md) |

## 사용자 지향 시스템

| 주제 | 문서 |
|---|---|
| 프런트엔드 셸 및 경로 | [frontend.md](frontend.md) |
| 프런트엔드 확장 지점 | [frontend_extensions.md](frontend_extensions.md) |
| UI 및 레이아웃 | [ui_and_layout.md](ui_and_layout.md) |
| 채팅 모듈 | [chat.md](chat.md) |
| 에이전트 런타임 | [agent_runtime.md](agent_runtime.md) |
| 팀 작업공간 런타임 | [multi-agent.md](./multi-agent.md) |
| 스케줄러 | [scheduler.md](scheduler.md) |

## 런타임 프리미티브

| 주제 | 문서 |
|---|---|
| 도구 | [tool.md](tool.md) |
| MCP | [mcp.md](mcp.md) |
| 흐름 엔진 | [flow.md](flow.md) |
| 프롬프트 및 시스템 프롬프트 배관 | [prompt.md](prompt.md) |
| 메모리 | [memory.md](memory.md) |
| 미디어 | [media.md](media.md) |
| AI 제공업체 | [ai-providers.md](ai-providers.md) |
| AI 클라이언트 | [ai_client.md](ai_client.md) |

## 통합 및 확장

| 주제 | 문서 |
|---|---|
| defaultspack 확장 | [extending.md](extending.md) |
| 입력 프로필 | [input-profiles.md](input-profiles.md) |
| 외부 입력 | [external-inputs.md](external-inputs.md) |
| 웹훅 | [webhooks.md](webhooks.md) |
| 게이트웨이 | [gateway.md](gateway.md) |
| 교통 | [transport.md](transport.md) |
| 기능 종속성 해결 | [capability/dependency-resolution.md](capability/dependency-resolution.md) |
