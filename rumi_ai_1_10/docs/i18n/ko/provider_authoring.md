<!-- docs-i18n-links:start -->
[EN](../../provider_authoring.md) | [JP](../ja/provider_authoring.md) | [KR](./provider_authoring.md) | [CN](../zh-cn/provider_authoring.md)
<!-- docs-i18n-links:end -->

# 제공자 작성

공급자 작성은 매니페스트 우선입니다. OpenAI 호환 공급자는 다음과 같아야 합니다.
공급자 매니페스트와 모델 정의 파일을 추가할 수 있습니다. Python 공급자
코드는 사용자 정의 프로토콜에만 필요합니다.

장소 제공자는 `extensions/llm/providers/<provider_id>/manifest.json`에 명시되어 있습니다.
또는 동일한 확장 레이아웃을 노출하는 설치된 카탈로그 팩. 모델 배치
`extensions/llm/providers/<provider_id>/models/*.json`에 따른 정의.

OpenAI 호환 공급자의 경우 다음을 설정합니다.

- `category: "llm_provider"`
- `adapter: "openai_compatible"`
- `api_key_env` 및 선택 사항 `base_url_env`
- `default_base_url`
- `default_model` 또는 `default_model_for`
- `streaming`, `vision`, `native_tool_calling` 등의 기능 메타데이터

모델 기능에는 알려진 경우 `vision`, `thinking`, `tool_calling`, `fast` 및 `knowledge_level`가 포함되어야 합니다. 라우팅은 이러한 필드에 따라 요청이 모델을 직접 사용할 수 있는지 또는 브리지 단계가 필요한지 결정합니다.

API 키는 기존 비밀/공급자 키 경로에 있어야 합니다. 프로필 작업 영역이나 공급자 매니페스트에 키를 저장하지 마세요. 공급자 테스트에서는 카탈로그 로드, 키 상태, 모델 기능 해결, 라우팅 호환성 및 오류 동작을 다루어야 합니다.

선별된 공급자 테이블은 누락된 레거시를 위한 호환성 대체입니다.
메타데이터. 새로운 공급자는 런타임 코드에 하드코딩된 행을 추가할 것을 요구해서는 안 됩니다.
