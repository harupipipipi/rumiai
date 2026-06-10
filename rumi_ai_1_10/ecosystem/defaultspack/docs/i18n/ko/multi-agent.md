<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](../ja/multi-agent.md) | [KR](./multi-agent.md) | [CN](../zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# 회사 작업공간 런타임

주요 회사 조정 경로는 `CompanySlackRuntime`이며 다음에서 구현됩니다.
`domain/company/message_router.py`에 내구성 있는 런타임 상태 포함
§루미§0§.

런타임은 Slack과 유사합니다.

- 채널과 스레드는 메시지를 보유합니다.
- 상담원에게 작업 라우팅을 언급합니다.
- 활성 에이전트 실행은 런타임 지침으로 언급을 받습니다.
- 유휴 에이전트는 `agent.delegate`을 통해 회사 업무를 위임받습니다.
- 회사 작업/스레드/메시지를 AgentEngine 실행에 연결하는 링크 실행
- 운영 관리자가 열려 있는 작업, 오래된 작업, 차단된 작업, 승인 대기 중인 작업을 검사합니다.
- 스크라이브 요약에는 회사, 채널, 스레드, 작업 및 실행 범위가 포함됩니다.

회사 계층에서는 도구를 실행하지 않습니다. 생성하고 라우팅하고 관찰합니다.
AgentEngine이 실행되어 정책, 승인, 모델 기능, 런타임 프로필 및
작업공간 신뢰 적용은 기존 에이전트/도구의 다운스트림으로 유지됩니다.
런타임.

## 레거시 호환성

`/api/agent/multi/*`은 호환성 래퍼로만 사용할 수 있습니다. 는
래퍼는 `CompanySlackRuntime`에 게시되고 `deprecation_warning`을 반환합니다.

`domain/agent/multi.py`은 레거시 전용입니다. 이는 기본 회사 런타임이 아닙니다.
