<!-- docs-i18n-links:start -->
[EN](../../permissions_policy.md) | [JP](../ja/permissions_policy.md) | [KR](./permissions_policy.md) | [CN](../zh-cn/permissions_policy.md)
<!-- docs-i18n-links:end -->

# 권한 정책

프로필 권한 파일은 기본값일 뿐입니다.

`grants.yaml`는 빈 상태로 시작됩니다. `tool_policy.yaml`은 기본적으로 네트워크를 거부하고 쓰기 작업 및 고위험 도구에 대한 승인을 요구하며 클라이언트가 제공한 승인 플래그를 거부합니다. `approvals.yaml`는 일회성 토큰이나 지속적인 승인 없이 시작됩니다.

최종 시행 경계는 기존 승인, 부여 및 기능 시스템으로 유지됩니다. 프로필 권한 파일은 고위험 도구 자체를 허용해서는 안 되며, 런타임 코드는 클라이언트가 제공한 `approved` 플래그를 신뢰해서는 안 됩니다.
