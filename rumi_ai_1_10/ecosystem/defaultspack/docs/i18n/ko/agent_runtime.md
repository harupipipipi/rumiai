<!-- docs-i18n-links:start -->
[EN](../../agent_runtime.md) | [JP](../ja/agent_runtime.md) | [KR](./agent_runtime.md) | [CN](../zh-cn/agent_runtime.md)
<!-- docs-i18n-links:end -->

# 내구성 있는 에이전트 런타임

defaultspack은 이제 `user_data/shared/agent_runtime/state.db`에 에이전트 실행을 기록합니다.
활성 기록 이벤트를 다음 JSONL 파일에 미러링합니다.
`user_data/shared/agent_runtime/transcripts/`.

기존 `defaults.agent.execute/status/approve/reject/cancel` API는 그대로 유지됩니다.
호환 가능. `blocks.agent._state`는 사용 가능한 경우 여전히 라이브 엔진을 유지하지만
프로세스 로컬 이후 `AgentRunStore`에서 `AgentEngine` 외관을 다시 만들 수 있습니다.
보류 중인 승인 실행을 포함하여 상태가 손실됩니다.

핵심 런타임 추가 사항은 일반적으로 유지됩니다: 파일 잠금, JSONL/SQLite 도우미, 런타임
이벤트 및 감사 수정 도우미. 에이전트 도메인 동작은
`domain/agent_runtime`.
