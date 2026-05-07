# Scheduler

`domain/scheduler` stores jobs in `user_data/shared/scheduler/jobs.json` and run
history in `user_data/shared/scheduler/runs/{job_id}.jsonl`.

Supported first-pass schedules are:

- `now`, `once`, `one_shot`
- `every 30m`, `every 1h`, `every 1d`
- simple five-field cron-like minute/hour forms

`no_agent` jobs execute a local script with a timeout and record stdout, stderr,
and return code. Agent jobs create a durable agent execution with a `cron:{job}`
session key.
