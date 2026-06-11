<!-- docs-i18n-links:start -->
[EN](../../flow_spec.md) | [JP](../ja/flow_spec.md) | [KR](./flow_spec.md) | [CN](../zh-cn/flow_spec.md)
<!-- docs-i18n-links:end -->

# 흐름 사양

흐름 문서에는 `flow_id`, 선택 사항 `version` 및 `description`, `inputs`, `outputs`가 있고 순서는 `steps`입니다.

표준 단계 유형은 `function`, `subflow`, `branch` 및 `parallel`입니다.
레거시 처리기/도구/프롬프트 단계는 호환 경로이므로 호환 경로가 아니어야 합니다.
새로운 defaultspack 흐름을 위한 제작 표면.

지원되는 기능 단계 필드:

- `id`: 안정적인 단계 식별자.
- `type`: `function`.
- `function`: `defaults.ai.complete`과 같은 함수 단계에 대한 호출 가능한 별칭입니다.
- `input`: 리터럴 값 또는 템플릿 참조.
- `when`: 선택적 조건식입니다.
- `output`: 해당 단계에서 작성한 변수 이름입니다.
- `on_error`: 선택적 오류 처리 정책.

프로필 범위 채팅 흐름은 프롬프트, 도구, 권한, 라우팅, 완료, 지속성 또는 감사 단계 전에 활성 프로필과 작업 영역을 로드해야 합니다. 권한 필터는 도구 지원 AI 호출 전에 실행되어야 합니다.

프롬프트 해결은 프롬프트 실행 단계가 아닌 기능 단계입니다. 표준
채팅 차례에 전화 `defaults.prompt.load_effective` 또는
`defaults.prompt.resolve_for_conversation` 후 프로필 작업공간이
그런 다음 해당 텍스트를 AI 요청 구성에 전달합니다. 효과적인 프롬프트
해결 방법은 프로필 재정의, 프로필 스냅샷, 팩 기본 우선 순위를 사용합니다.
