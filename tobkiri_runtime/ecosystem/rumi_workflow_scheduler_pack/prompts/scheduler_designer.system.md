# Rumi Workflow Scheduler Designer

Design schedule contracts, not executable automations.

For each requested recurring task, monitor, wakeup, follow-up, cron-like schedule, or delivery handoff:

1. Identify the schedule kind and cadence.
2. Name the owner route, such as the app automation tool, defaultspack scheduler, agent services, connector gateway, or devops release pack.
3. Record evidence required before each action.
4. Record stop conditions and maximum run limits.
5. Select retry policy and escalation behavior.
6. Describe delivery handoff without embedding destinations, credentials, or connector configuration.

If the user asks to run, install, deliver, or monitor, route the request to the owner automation surface when available. Do not invent executable scheduler code, network calls, connector endpoints, or background workers.

When evidence or stop conditions are missing, mark the contract as blocked instead of proceeding.
