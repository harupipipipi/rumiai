<!-- docs-i18n-links:start -->
[EN](../../input-dispatcher.md) | [JP](../ja/input-dispatcher.md) | [KR](./input-dispatcher.md) | [CN](../zh-cn/input-dispatcher.md)
<!-- docs-i18n-links:end -->

# 입력 디스패처

`submit_input`은 공개 호환성 진입점으로 남아 있지만 표준
현재 경로는 다음과 같습니다.

```text
RumiInputEnvelope
  -> dispatch_input
  -> action_registry
  -> delivery.action_id handler
```

## 봉투 모양

모든 인바운드 회전은 `RumiInputEnvelope`로 정규화됩니다.

- `source`: 누가 또는 무엇이 입력을 생성했는지
- `target`: 대화, 경로 또는 런타임 대상
- `delivery`: 액션 선택 메타데이터
- `input`: 기본 텍스트 페이로드
- `params`: 작업별 구조화된 데이터
- `tools`: 선택적 명시적 도구 선택
- `attachments`: 턴과 함께 운반되는 파일 또는 이미지
- `metadata`: 감사 및 공급자 메타데이터

`delivery.action_id`의 기본값은 `chat.message`입니다.

## 내장 액션

- `chat.message`: 일반적인 사용자 메시지 흐름
- `run.instruction`: 런타임 조향/명령을 대기열에 넣습니다.
- `run.interrupt`: 향후 일시 중지/취소/리디렉션 의미를 위한 공간이 있는 긴급 런타임 명령
- `agent.delegate`: 구조화된 페이로드에서 하나의 위임 에이전트 실행을 시작합니다.
- `model.switch`: 대화 기본 모델 변경 유지
- `model.route`: 회전 범위 경로 무시 설정

알 수 없는 `delivery.action_id` 값은 대신 구조화된 오류를 반환합니다.
공급자별 논리를 따르지 않습니다.

## 호환성

- 기존 `submit_input(...)` 호출자는 계속 작동합니다.
- 기존 채팅 보내기 동작은 여전히 동일한 상점과 블록을 통해 라우팅됩니다.
- 레거시 `subagent` 명명된 호출 사이트는 이제 `agent.delegate`을 사용하거나
`model.call` 스타일 유틸리티 라우팅이 내부적으로 수행됩니다.
