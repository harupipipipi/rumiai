<!-- docs-i18n-links:start -->
[EN](../../model-packs.md) | [JP](../ja/model-packs.md) | [KR](./model-packs.md) | [CN](../zh-cn/model-packs.md)
<!-- docs-i18n-links:end -->

# 모델 팩 및 `model.call`

모델 라우팅은 이제 일반 모델 ID 외에도 `modelpack/<id>`을 지원합니다.
레거시 복합 모델.

## 모델 팩 모양

`ModelPack`은 작은 라우팅 매니페스트입니다.

- `id`
- `display_name`
- `members`
- `rules`
- `fallback`
- 선택적인 예산, 안전 및 메타데이터

첫 번째 구현은 폴백 체인 스타일 선택에 중점을 두고 있지만
앙상블 또는 리뷰 체인 모드를 위한 공간을 유지합니다.

## 해상도

`ModelRouter` 및 `AIClient`은 현재 턴을 사용하여 `modelpack/<id>`를 해결합니다.

- 이미지 입력/비전 요구 사항
- 도구 호출 요구 사항
- 요구되는 사고수준
- 작업 힌트
- 맞춤형 팩 규칙
- 대체 멤버

레거시 `composite_models`은 호환성을 유지하며 내부 장치로 처리될 수 있습니다.
팩 같은 구조.

## §루미§0§

`model.call`은 "다른 모델에 질문하기"에 대한 제한된 유틸리티 경로입니다.

- 기본적으로 도구 액세스가 없습니다.
- `required_capabilities`, `model_hint`, `output_schema`, `max_tokens` 허용
  그리고 §루미§0§
- 전달하기 전에 숨겨진 메타데이터와 비밀을 제거합니다.
- 재귀 깊이 제한을 적용합니다.

다음과 같이 경계를 사용하십시오.

- `model.call`: 다른 모델에 대한 제한된 질문
- `agent.delegate`: 위임된 도구 가능 작업
- `model.switch`: 지속 대화 기본 변경
- `model.route`: 회전 범위 라우팅 무시
