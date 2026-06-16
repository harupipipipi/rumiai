# Operations

## Installation

Install through the setup-pack selector as `rumi_workflow_scheduler_pack`. The setup metadata marks the pack as optional and not eligible for automatic all-ok grants.

Expected prerequisite:

- `defaultspack >=2.0.0`

Optional companion packs may provide execution targets or reviewed handoff surfaces:

- `rumi_agent_services_pack`
- `rumi_connector_gateway_pack`
- `rumi_devops_release_pack`

## Development

Keep the pack declarative. New executable schedulers, cron runners, queue workers, message delivery clients, network monitors, functions, routes, handlers, stores, or background daemons are outside this pack's current scope.

When changing behavior, update the matching files:

- `catalog/schedule_contracts.yaml` for schedule types and required fields.
- `catalog/workflow_routes.yaml` for owner routing and overlap behavior.
- `catalog/delivery_handoffs.yaml` for handoff targets and channel posture.
- `catalog/scheduler_schema.json` for local record shape.
- `policies/retry_policy.yaml` for retry, backoff, evidence, and stop conditions.
- `profiles/`, `prompts/`, and `presets/` for user-facing design behavior.
- `examples/` for sample schedule records.

## Tests

Run the focused contract test:

```bash
python -m pytest rumi_ai_1_10/tests/test_rumi_workflow_scheduler_pack_contract.py
```

## Common Failure Modes

- The pack starts running schedules instead of describing them. Execution belongs to owner runtimes.
- A delivery example includes a real destination, credential, or endpoint. Keep examples local and placeholder-only.
- Retry policy lacks stop conditions. Recurring workflows must have evidence and termination criteria.
- Setup metadata becomes all-ok eligible. Scheduling and delivery should remain opt-in and owner-approved.
- Overlap text implies this pack owns defaultspack, agent services, connector gateway, or release enforcement.

## Change Review Checklist

- Required docs from `rumi_ai_1_10/docs/pack-documentation-contract.md` still exist.
- JSON and YAML assets parse.
- No executable code was added.
- No secrets or credential-like literals were added.
- Network remains none by default.
- Overlap with defaultspack, agent services, connector gateway, and devops release packs remains contract-only.
