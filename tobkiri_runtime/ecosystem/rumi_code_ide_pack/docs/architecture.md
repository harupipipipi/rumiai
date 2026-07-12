# Architecture

## Responsibility

`rumi_code_ide_pack` packages advanced code, CLI, and IDE workflow configuration. Its responsibility is to describe how an agent should use existing Rumi coding capabilities during repository work: inspect first, plan when useful, patch narrowly, run targeted checks, preserve user changes, and explain residual risk.

## Non-Responsibility

The pack does not implement file IO, terminal execution, git operations, browser automation, stores, routes, handlers, or approval enforcement. Those remain owned by `defaultspack`, `rumi_default_tools_pack`, and the runtime.

## Directory Layout

- `ecosystem.json`: pack identity, dependencies, asset index, and declarative-only component boundary.
- `profiles/`: runtime profile metadata for CLI, IDE pairing, and review sessions.
- `prompts/`: system prompt layers for coding-agent behavior.
- `presets/`: named workflow bundles inspired by code-first agent surfaces.
- `examples/`: example sessions that demonstrate intended use.
- `command_recipes/`: reusable command/task recipes with approval posture.
- `tool_scopes/`: metadata describing allowed, approval-gated, and excluded tool families.
- `metadata/`: overlap and conflict notes.
- `docs/`: pack-specific documentation.

## Execution Path

1. A user installs or selects the pack through setup-pack metadata.
2. The runtime discovers its declarative assets.
3. A profile or preset points to defaultspack graph and flow primitives such as `defaultspack.coding_workspace` and `agent_chat`.
4. The active agent uses prompts, command recipes, and tool scope metadata to guide how existing tools are selected and approved.

## Runtime Contact Points

- Graph/flow dependency: `defaultspack.coding_workspace` and `agent_chat`.
- Tool dependency: concrete file, terminal, git, todo, subagent, and browser companion tools from `rumi_default_tools_pack`.
- Policy dependency: default approval and audit behavior from the host runtime.

No pack-owned Python modules are imported during normal use.
