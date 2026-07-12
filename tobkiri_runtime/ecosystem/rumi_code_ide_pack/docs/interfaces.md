# Interfaces

## Flows, Functions, Handlers, Routes, Events, Stores

This pack declares no pack-owned flows, modifiers, functions, handlers, HTTP routes, runtime events, or stores.

It references these existing runtime interfaces:

- `agent_chat` flow from `defaultspack`.
- `defaultspack.coding_workspace` graph.
- File, terminal, git, todo, subagent, and browser companion tool families supplied by `rumi_default_tools_pack`.

## Profiles

- `rumi_code_ide_pack.code_cli_ide`: primary CLI/IDE workspace profile.
- `rumi_code_ide_pack.code_review_terminal`: review-first terminal profile.
- `rumi_code_ide_pack.local_first_pair_programmer`: conservative local-first pairing profile.

## Prompts

- `code_ide_agent.system.md`: main repository-editing behavior.
- `code_review_terminal.system.md`: review and risk identification behavior.
- `command_recipe_runner.system.md`: recipe interpretation and command discipline.

## Presets

The presets are named after workflow styles, not vendor compatibility modes. They tune behavior for patch loops, discovery-heavy CLI usage, IDE pairing, and strict local-first work.

## Command Recipes

`command_recipes/code_cli_recipes.yaml` provides declarative recipes. Recipes are suggestions for how an agent should plan and verify work; they are not executable scripts and do not contain secrets.

## Tool Scope Metadata

`tool_scopes/code_ide_tool_scope.yaml` describes allowed, approval-gated, and excluded tool categories. Enforcement remains the runtime's job.

## Required Secrets

None.

## Network

No network access is required by this pack. Existing tools may request network access only according to their own manifests and runtime approvals.

## Grants

The setup pack is not `supports_all_ok` eligible. Installing it should not automatically grant new tool powers. It depends on the user's existing grants for defaultspack and default tools.

## Dependencies

- Required: `defaultspack >=2.0.0`.
- Required: `rumi_default_tools_pack >=1.0.0`.
- Optional: `rumi_local_agent_pack >=1.0.0`.

## Overlap And Conflict Notes

- With `defaultspack`: this pack uses defaultspack's graph, flow, profile, and policy primitives. It does not redefine them.
- With `rumi_default_tools_pack`: this pack scopes and documents concrete tools from that pack. It does not ship replacement tools.
- With `rumi_local_agent_pack`: both packs contain coding-oriented prompts and presets. Use this pack when the desired surface is advanced code/CLI/IDE customization; use `rumi_local_agent_pack` for broader local-agent starter behavior.
- If duplicate profile or preset names appear in a UI, prefer fully qualified pack IDs and keep `rumi_code_ide_pack.*` assets opt-in.
