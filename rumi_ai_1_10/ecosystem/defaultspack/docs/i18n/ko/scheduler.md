<!-- docs-i18n-links:start -->
[EN](../../scheduler.md) | [JP](../ja/scheduler.md) | [KR](./scheduler.md) | [CN](../zh-cn/scheduler.md)
<!-- docs-i18n-links:end -->

# 스케줄러

`domain/scheduler`는 작업을 `user_data/shared/scheduler/jobs.json`에 저장하고 실행합니다.
`user_data/shared/scheduler/runs/{job_id}.jsonl`의 역사.

지원되는 첫 번째 통과 일정은 다음과 같습니다.

- `now`, `once`, `one_shot`
- `every 30m`, `every 1h`, `every 1d`
- 간단한 5개 필드 cron과 같은 분/시간 형식

`no_agent` 작업은 기본적으로 비활성화되어 있습니다. 런타임 구성이 설정된 경우에만 실행됩니다.
`tool_policy.allow_shell=true` 및
`scheduler.allow_no_agent_scripts=true`, 명령은 argv 목록이어야 합니다.
그 실행 파일은 `scheduler.no_agent_command_allowlist`에 있습니다. 는
러너는 `shell=True`를 절대 사용하지 않습니다. 에이전트 작업은 다음을 사용하여 지속 가능한 에이전트 실행을 생성합니다.
`cron:{job}` 세션 키.
