# Architecture

## Responsibility

Rumi Agent Services Pack describes service-style multi-agent workflows on top of existing Rumi runtime and tool packs. It names roles, capability bundles, routing rules, handoff payloads, task presets, and example task declarations.

The pack does not own runtime execution. It does not ship handlers, routes, functions, stores, or tool executors. Existing packs remain responsible for chat turns, planning, tool policy, approval, workspace access, browser/computer control, web search, subagents, and file operations.

## Directory Map

- `ecosystem.json`: component inventory and load-order hints for this declarative pack.
- `profiles/`: runtime profile declarations for service roles.
- `prompts/`: system prompts that define service role behavior.
- `presets/`: named compositions for user-facing agent service modes.
- `coordination/`: routing matrix, workflow templates, handoff contract, role taxonomy, and guardrails.
- `catalog/capabilities.yaml`: service-facing capability names mapped to expected underlying local capabilities.
- `examples/`: sample task specs that can be copied into project setup or tests.
- `docs/`: pack-specific documentation required by the pack documentation contract.

## Runtime Contact Points

The pack expects these existing capabilities to be available when a runtime chooses to execute a preset:

- `defaultspack`: chat, planning, approval policy, compacting, memory, and flow runtime basics.
- `rumi_default_tools_pack`: file, terminal, git, browser, search, todo, subagent, and artifact tools.
- `rumi_local_agent_pack`: base local-agent profiles and prompts.

The specs use capability names, not direct imports. This keeps the pack portable and prevents it from duplicating defaultspack core.

## Service Model

The service model has five layers:

1. Intake: clarify goal, constraints, workspace, network posture, and deliverable.
2. Director: decompose the task into role-specific work packages.
3. Worker roles: research, coding, browser operation, artifact drafting, and review.
4. Coordination: handoffs use explicit inputs, outputs, evidence, open questions, and approval needs.
5. Delivery: final response includes completed work, evidence, verification, limitations, and next actions.

## Local-First Boundary

Every profile defaults to local workspace context and approval-gated tool use. Network activity is optional, denied by default, and must be enabled by a runtime policy or explicit user approval. Secrets are never declared in this pack.
