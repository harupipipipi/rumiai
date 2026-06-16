# Operations

## Installation

Install through the setup-pack selector as `rumi_code_ide_pack`. The setup metadata marks the pack as optional and not eligible for automatic all-ok grants.

Expected prerequisites:

- `defaultspack >=2.0.0`
- `rumi_default_tools_pack >=1.0.0`

## Development

Keep changes declarative unless a separate implementation task explicitly expands the pack scope. New runtime handlers, functions, routes, or stores require updating this documentation and the pack contract.

When changing workflow behavior, update the matching files:

- Profiles for surface, graph, flow, node, or policy defaults.
- Prompts for agent behavior.
- Presets for named workflow bundles.
- Command recipes for task-level command guidance.
- Tool scopes for allow/approval/exclusion metadata.
- Overlap metadata when another pack owns nearby behavior.

## Testing

Run the pack contract test after edits:

```bash
python -m pytest rumi_ai_1_10/tests/test_rumi_code_ide_pack_contract.py
```

## Common Failure Modes

- Missing docs required by `rumi_ai_1_10/docs/pack-documentation-contract.md`.
- Setup-pack metadata points at a target pack ID that does not exist.
- A profile claims to own a defaultspack graph or flow instead of referencing it as a dependency.
- A recipe becomes an executable script or includes destructive commands without approval notes.
- Tool scope metadata implies enforcement that the runtime does not provide.

## Change Checklist

- Confirm no secrets or credentials were added.
- Confirm `ecosystem.json` and setup `pack.json` agree on pack ID, target pack ID, version, and dependencies.
- Confirm overlap notes still mention `defaultspack`, `rumi_default_tools_pack`, and `rumi_local_agent_pack`.
- Run the contract test.
