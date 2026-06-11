<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](../ja/multi-agent.md) | [KR](./multi-agent.md) | [CN](../zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# 팀 작업공간 런타임

사용자가 접하는 기본 조정 경로는 팀 작업 영역 런타임입니다.
내부적으로는 여전히 `CompanySlackRuntime`을 중심으로 구현됩니다.
`domain/company/message_router.py`에서 내구성 있는 런타임 상태로 구현됨
`domain/company/runtime_store.py`.

런타임은 Slack과 유사합니다.

- 채널과 스레드는 메시지를 보유합니다.
- 상담원에게 작업 라우팅을 언급합니다.
- 활성 에이전트 실행은 런타임 지침으로 언급을 받습니다.
- 유휴 에이전트는 `agent.delegate`를 통해 위임된 팀 작업을 받습니다.
- 링크를 실행하면 회사 호환성 기록과 팀 스레드/메시지가 연결됩니다.
  AgentEngine 실행
- 운영 관리자는 공개, 부실, 차단 및 승인 대기를 검사합니다.
  일
- 스크라이브 요약은 작업 공간, 채널, 스레드, 작업 및 실행 범위를 다룹니다.

회사 계층에서는 도구를 실행하지 않습니다. 생성하고 라우팅하고 관찰합니다.
AgentEngine이 실행되어 정책, 승인, 모델 기능, 런타임 프로필 및
작업공간 신뢰 적용은 기존 에이전트/도구의 다운스트림으로 유지됩니다.
런타임.

## 용어 참고 사항

- `delegation`은 작업을 다른 에이전트에게 보내는 정식 작업 이름입니다.
  런타임 측면에서 이는 `agent.delegate`에 매핑됩니다.
- `subagent`은 위임된 제품에 대한 호환성 또는 레거시 라벨로 읽어야 합니다.
  별도의 기본 런타임 아키텍처로 작동하지 않습니다.
- `company`은 코드 경로, ID 및 이전 경로에서 일반적으로 사용됩니다. 문서는 사용
`team workspace`는 사용자가 바라보는 표면을 설명할 때 사용됩니다.

## 레거시 호환성

`/api/agent/multi/*`은 호환성 래퍼로만 사용할 수 있습니다. 는
래퍼는 `CompanySlackRuntime`에 게시되고 `deprecation_warning`을 반환합니다.

`domain/agent/multi.py`은 레거시 전용입니다. 기본 팀 작업 공간이 아닙니다.
런타임.
