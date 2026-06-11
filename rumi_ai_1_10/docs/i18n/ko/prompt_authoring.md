<!-- docs-i18n-links:start -->
[EN](../../prompt_authoring.md) | [JP](../ja/prompt_authoring.md) | [KR](./prompt_authoring.md) | [CN](../zh-cn/prompt_authoring.md)
<!-- docs-i18n-links:end -->

# 프롬프트 작성

Rumi의 제품 어휘에서는 항상 로드되는 지침에 대해 `rule`을 선호하고
`skill` 트리거 또는 주문형 지침/워크플로 번들용.

`prompt`은 조립된 원시 모델 입력 텍스트에 대한 하위 수준 런타임 용어입니다.
실행 시간에. `system prompt`은 시스템 역할의 전송/API 형식입니다.
사용자에게 대면하는 주요 개념이 아닌 프롬프트 텍스트입니다.

프롬프트는 수동적인 텍스트 리소스입니다. AI 요청에 대한 동작을 설명합니다.
하지만 모델을 선택하거나, 도구를 검색하거나, 권한을 부여하거나, 전화를 걸지는 않습니다.
공급자를 선택하거나 자체적으로 런타임 상태를 변경합니다.

각 프롬프트에는 안정적인 프롬프트 ID, 콘텐츠, 소유자 팩 또는 프로필이 필요합니다.
린트/압축 기대.

효과적인 프롬프트 우선순위는 다음과 같습니다.

1. `profiles/<profile_id>/prompts/`의 프로필 재정의.
2. `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/`의 프로필 스냅샷.
3. defaultspack 프롬프트 구성 요소 또는 프롬프트 확장에서 기본값을 압축합니다.

프로필 재정의는 사용자 소유의 작업공간 프롬프트 파일이며 다음과 같이 보고됩니다.
`source_chain`의 `profile_override` 레이어. 스냅샷은 팩 프롬프트를 유지합니다.
프로필이 생성될 때 캡처된 버전입니다. 팩 기본값은 대체입니다.
프로필별 프롬프트가 없는 경우.

`defaults.prompt.load_effective`는 선택한 소스, `source_type`를 반환합니다.
`source_chain`, 원시 `content` 및 `final_content`. `defaults.prompt.resolve_for_conversation`
동일한 우선순위를 사용한 다음 대화 변수를 최종 변수로 렌더링합니다.
내용.

`execution.type="prompt"`으로 도구를 제작하지 마세요. 프롬프트는 수동적으로 유지됩니다. 사용
렌더링된 프롬프트 텍스트가 필요할 때 흐름/기능의 `defaults.prompt.render`.

프롬프트 린팅을 통해 중복성, 누락된 역할 컨텍스트 및 토큰 예산을 표시해야 합니다.
위험. 압축은 안전, 허가 및 도구 사용 제약 조건을 보존해야 합니다.

문서나 UI 사본을 작성할 때 `rules` 측면에서 작성된 동작을 설명하고
`skills`, 런타임에 대해 논의할 때만 `prompt` 또는 `system prompt`을 설명하십시오.
어셈블리, 공급자 페이로드 또는 디버깅.
