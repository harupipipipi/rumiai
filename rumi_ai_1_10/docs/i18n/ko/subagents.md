<!-- docs-i18n-links:start -->
[EN](../../subagents.md) | [JP](../ja/subagents.md) | [KR](./subagents.md) | [CN](../zh-cn/subagents.md)
<!-- docs-i18n-links:end -->

# 위임 호환성

Rumi는 더 이상 "하위 에이전트"를 기본 아키텍처 개념으로 취급하지 않습니다.

사용자에게 표시되는 문구의 경우 다음을 선호합니다.

- `team workspace` 장기 실행 다중 에이전트 작업 공간 표면
- `team` 해당 작업 공간 내부의 협력 에이전트 세트
- 제한된 작업을 다른 에이전트에게 보내는 `delegation`
- 범위가 좁은 작업자 역할의 경우 `specialist` 또는 `delegated agent`

`company` 및 `subagent`은 이전 API,
경로, 저장된 식별자 또는 문서에서는 여전히 이를 사용합니다.

표준 런타임 계약은 다음과 같습니다.

- `chat.message`: 일반 대화 입력
- `run.instruction`: 대기열 조정 또는 런타임 안내
- `run.interrupt`: 긴급 런타임 안내
- `agent.delegate`: 하나의 위임된 도구 지원 실행
- `model.call`: 기본적으로 도구가 없는 하나의 제한된 모델 간 질문
- `model.switch`: 지속적인 대화 모델 변경
- `model.route`: 턴 범위 라우팅 무시

`subagent`은 이전 버전의 호환성 이름 및 사용자용 별칭으로 유지됩니다.
여전히 위임된 작업을 참조하는 경로, 기능, 도구, 레이블 및 문서.

## 현재 경계

- `agent.delegate` = 도구, 승인 및 일반 런타임 정책을 사용할 수 있는 위임된 실행 1개
- `multi-agent` = 둘 이상의 위임된 작업자에 대한 조정된 그룹 실행
- `tool_selector`, `prompt_compactor`, `context_summarizer`, `model_router` 및 `vision_ocr`와 같은 유틸리티 역할은 특수 하위 에이전트 프레임워크가 아닌 `model.call` 스타일 유틸리티 라우팅을 통해 구현됩니다.

## 호환성 경로

다음과 같은 호환성 표면은 계속 사용 가능합니다.

- `/api/agent/subagent`
- `defaults.agent.run_subagent`
- `defaultspack.agent.run_subagent`
- `defaults.tool.subagent`
- `defaultspack.tool.subagent`
- `rumi_default_tools_pack`의 `subagent` 아동 대화 도구

이전 버전과의 호환성을 위해 유지되며 공유 입력을 통해 라우팅되어야 합니다.
병렬 동작을 도입하는 대신 모델, 도구 및 정책 계약을 수행합니다.

실제로 이는 다음을 의미합니다.

- 유틸리티 역할 호환성 통화는 공유된 `model.call` 스타일 유틸리티 라우팅을 통해 라우팅됩니다.
- 작업과 유사한 호환성 호출은 `agent.delegate`과 같이 공통 입력 디스패처를 통해 라우팅됩니다.

이전 문서에 `company workspace`이라고 적혀 있으면 오늘의 `team workspace`로 읽어보세요.
텍스트가 호환성 API 또는 저장된 런타임을 구체적으로 설명하지 않는 한
식별자.

## 정책 및 승인

호환성 `subagent` 별칭을 사용해도 다음을 우회하지 않습니다.

- 도구 정책
- 승인 게이트
- 런타임 프로필 도구 연결
- 모델 능력 점검
- 작업 공간 신뢰 요구 사항

위임된 작업에 도구가 필요한 경우 다른 작업과 동일한 정책 및 승인 경로를 사용해야 합니다.
다른 실행.
