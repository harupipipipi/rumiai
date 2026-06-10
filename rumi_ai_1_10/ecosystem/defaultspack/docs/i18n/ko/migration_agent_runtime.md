<!-- docs-i18n-links:start -->
[EN](../../migration_agent_runtime.md) | [JP](../ja/migration_agent_runtime.md) | [KR](./migration_agent_runtime.md) | [CN](../zh-cn/migration_agent_runtime.md)
<!-- docs-i18n-links:end -->

# 에이전트 런타임 마이그레이션

기존 공개 에이전트 또는 채팅 API는 제거되지 않았습니다.

호환성 동작:

- 이전 `defaults.agent.execute`은 동일한 봉투 및 실행 페이로드를 반환합니다.
- 기존 `defaults.agent.approve/reject/status/cancel`에서는 여전히 `execution_id`을 사용합니다.
- 오래된 인메모리 엔진은 프로세스가 살아있는 동안 계속 작동합니다.
- 누락된 메모리 내 엔진은 가능한 경우 `AgentRunStore`에서 해결됩니다.
- 이전 메모리 호출은 `MemoryStore`을 통해 계속되고 Memory2로 미러링됩니다.

런타임은 다음을 통해 기능 플래그 친화적입니다.
`config/default_runtime_config.json` 및 옵션
`user_data/shared/runtime_config.json`은 무시되지만 이 패치는
레거시 API 형태가 유지되므로 기본적으로 내구성 있는 저장소가 활성화됩니다.
