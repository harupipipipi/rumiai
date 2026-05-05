# Agent Factory

Agent Factory generalizes the fixed Operations Company roles into user-created `AgentDefinition` records. It provides CRUD, lifecycle, templates, run history, and policy-aware tick execution.

## Definition

```yaml
agent_id: research_monitor_1
display_name: Research Monitor
profile_id: defaultspack.operations_company
role_key: research_specialist
enabled: true
system_prompt: Monitor the requested sources and report only important changes.
model_policy: {}
api_key_policy: {}
tool_policy: {}
runtime_policy: {}
schedule_policy: {}
stop_conditions: {}
memory_policy: {}
```

Definitions are stored in shared user data and can be created from templates:

```text
browser_operator
computer_operator
research_monitor
coding_engineer
reviewer
scheduler
operations_monitor
custom
```

## Runtime

`AgentRuntime.tick(agent_id)` loads the definition, resolves policy, checks lifecycle guards, records run history, and returns one of:

```text
idle
running
paused
blocked
failed
completed
```

Stop conditions include runtime, cost, token, failure count, no-change ticks, approval required, and login required. Blocker reasons include login, captcha, 2FA, payment, external send, and sensitive confirmation.

## Policy

Policy precedence is:

```text
hard safety deny >
profile policy >
agent policy >
role policy >
user selected tools >
session approval >
one-time approval
```

Deny always wins over allow. Budget exhaustion tries fallback keys before blocking the run.

## Routes

| method | path |
|---|---|
| `GET/POST` | `/api/agents` |
| `GET/PUT/DELETE` | `/api/agents/{agent_id}` |
| `POST` | `/api/agents/{agent_id}/start` |
| `POST` | `/api/agents/{agent_id}/pause` |
| `POST` | `/api/agents/{agent_id}/resume` |
| `POST` | `/api/agents/{agent_id}/stop` |
| `POST` | `/api/agents/{agent_id}/tick` |
| `GET` | `/api/agents/{agent_id}/status` |
| `GET` | `/api/agents/{agent_id}/runs` |
| `GET` | `/api/agents/{agent_id}/logs` |

The Operations panel uses these routes for Create Agent, dashboard, lifecycle controls, and run inspection.
