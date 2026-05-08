# Scheduler

`domain/scheduler` stores jobs in `user_data/shared/scheduler/jobs.json` and run
history in `user_data/shared/scheduler/runs/{job_id}.jsonl`.

Supported first-pass schedules are:

- `now`, `once`, `one_shot`
- `every 30m`, `every 1h`, `every 1d`
- simple five-field cron-like minute/hour forms

`no_agent` jobs are disabled by default. They only run when runtime config sets
both `tool_policy.allow_shell=true` and
`scheduler.allow_no_agent_scripts=true`, and the command must be an argv list
whose executable is present in `scheduler.no_agent_command_allowlist`. The
runner never uses `shell=True`. Agent jobs create a durable agent execution with
a `cron:{job}` session key.
