<!-- docs-i18n-links:start -->
[EN](../../prompt.md) | [JP](../ja/prompt.md) | [KR](./prompt.md) | [CN](../zh-cn/prompt.md)
<!-- docs-i18n-links:end -->

# 프롬프트 디자인

프롬프트는 수동적인 텍스트 레이어입니다. 저장, 검증, 해결 및 렌더링합니다.
프롬프트 템플릿이지만 도구 선택, 권한 부여, AI 선택은 수행되지 않습니다.
공급자, 호출 모델 또는 채팅 상태 자체를 변경합니다.

## 효과적인 프롬프트 우선순위

`defaults.prompt.load_effective` 및
`defaults.prompt.resolve_for_conversation`는 동일한 우선순위를 사용합니다:

1. 작업공간 프롬프트 디렉터리에서 프로필 재정의
   `profiles/<profile_id>/prompts/`.
2. 프로필 스냅샷
   `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/`.
3. defaultspack 프롬프트 구성 요소 또는 프롬프트 확장에서 기본값을 압축합니다.

작업공간 프롬프트 파일은 공식적인 `profile_override` 레이어입니다. 그것은
사용자 소유이며 스냅샷을 확보합니다. 모든 효과적인 프롬프트 응답에는 다음이 포함됩니다.
`source_type`, `source`, `source_chain`, `content`, `final_content`이므로 흐름이 됩니다.
단계에서는 어떤 레이어가 최종 텍스트를 생성했는지 감사할 수 있습니다.

## 기능

- `defaults.prompt.load_effective`는 선택한 프롬프트 텍스트와 소스를 반환합니다.
  대화 변수를 렌더링하지 않고 체인을 연결합니다.
- `defaults.prompt.resolve_for_conversation`는 동일한 효과적인 프롬프트를 해결합니다.
  명시적 `variables` 및 수동 변수에서 `{{...}}` 변수를 렌더링합니다.
  `context.*` 값(예: `context.profile_id`, `context.conversation_id`,
  `context.message_count` 및 `context.messages`.
- `defaults.prompt.validate_template`는 템플릿 구문을 검증하고 사용자를 보고합니다.
  변수, 컨텍스트 변수, 선언된 변수, 경고 및 오류.
- `defaults.prompt.render`는 제공된 명시적 프롬프트/템플릿을 렌더링합니다.
  변수.

## 작성 규칙

프롬프트 템플릿은 `{{variable}}` 및 `{{context.variable}}` 자리 표시자를 사용할 수 있습니다.
누락된 변수는 렌더러에 의해 텍스트에 남아 있습니다. 유효성 검사를 사용하여
흐름이 실행되기 전에 이를 감지합니다.

프롬프트 작성으로 실행 가능한 도구를 생성해서는 안 됩니다. `execution.type="prompt"`는
레거시 호환성 경로일 뿐이며 제작 표면이 아닙니다. 워크플로우라면
렌더링된 프롬프트 텍스트가 필요하면 흐름/함수에서 `defaults.prompt.render`을 호출하세요.
도구가 필요한 경우 `rumi_function` 또는 `capability` 도구 외관을 작성하세요.

프롬프트 파일은 데이터입니다. 파일을 읽고, 공급자를 호출하거나,
터치 호스트 기능은 프롬프트 작성에 속하지 않습니다. 그 논리는 살아 있어야 해
신뢰할 수 있는 기능과 명시적인 기능 부여 뒤에 있습니다.
