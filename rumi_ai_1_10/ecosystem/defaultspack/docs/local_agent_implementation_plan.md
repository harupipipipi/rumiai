# Local Agent Implementation Plan

## P0

- Capability catalog: load `capabilities/*.capability.yaml` and expose `/api/capabilities`.
- Local agent profile: load `profiles/local_agent.profile.yaml` and expose it in `/api/agent-service/manifest`.
- Plan and step: use `schemas/agent_plan.schema.yaml`, `schemas/agent_step.schema.yaml`, and `blocks.agent.plan`.
- File workspace: keep all operations inside workspace root; expose read, write, create, delete, list, search, diff, snapshot, restore.
- Terminal and git: classify risk, require approval fields for execution, and audit attempted actions.
- Safety: default network deny, redact secrets, and record audit metadata.

## P1

- Memory and project context: local JSON/file storage with review and delete operations.
- Compact: rolling summaries, pinned context, and restore notes.
- Artifacts: create local markdown/text/code/json/yaml/html/csv artifacts with metadata.

## P2

- Research: local sources first, optional web/browser providers later.
- UI: panels for plan, tool calls, file tree, diff, terminal, artifacts, memory, and approvals.

## Tests

- Validate catalog file loading.
- Verify routes exist in fallback HTTP registry.
- Verify profile and capability policy metadata.
- Verify workspace safety and approval metadata for risky operations.
