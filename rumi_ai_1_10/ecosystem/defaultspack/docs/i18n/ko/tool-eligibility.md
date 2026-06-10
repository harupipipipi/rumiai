<!-- docs-i18n-links:start -->
[EN](../../tool-eligibility.md) | [JP](../ja/tool-eligibility.md) | [KR](./tool-eligibility.md) | [CN](../zh-cn/tool-eligibility.md)
<!-- docs-i18n-links:end -->

# 도구 적격성 및 차단 이유

도구 가용성은 이제 두 곳에서 계산됩니다.

1. 채팅/에이전트 준비 중 사전 제공자 필터링
2. 필터링된 도구가 여전히 호출되는 경우 실행 시간 거부

## 런타임 기능 스냅샷

매 턴마다 정규화된 토큰으로 `RuntimeCapabilitySnapshot`을 기록합니다.

- 입력 특성: `input.text`, `input.image`, `input.file`
- 모델 기능: `model.text`, `model.image_input`, `model.tool_calling`,
  §루미§0§, §루미§1§
- 런타임 기능
- 정책 역량
- 태그

이 데이터는 일반적인 대화에 삽입되지 않고 메타데이터/이벤트에 저장됩니다.
텍스트.

## 도구 요구 사항

도구 정의는 다음을 선언할 수 있습니다.

- `capability_requirements.requires_all`
- `capability_requirements.requires_any`
- `capability_requirements.forbids`
- `requires_model_capabilities`
- `requires_input_modalities`
- `requires_runtime_capabilities`
- `attachment_policy`
- `supports_attachments`

## 안정적인 이유 코드

차단되거나 거부된 도구는 안정적인 이유 코드를 사용합니다.

- `missing_capability`
- `missing_input`
- `model_unsupported`
- `disabled_by_user`
- `disabled_by_policy`
- `requires_approval`
- `not_connected_to_profile`
- `requires_trusted_workspace`
- `missing_api_key`
- `attachment_not_supported`
- `risk_blocked`

실행 시간 거부는 다음과 같은 구조화된 결과를 반환합니다.

- `status: rejected`
- 공급자에게 안전함 `code`
- `reason`
- `required`
- `actual`
- `repair_suggestions`
