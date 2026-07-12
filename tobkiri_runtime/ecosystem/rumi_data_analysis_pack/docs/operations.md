# Operations

## Install

Install this optional setup pack after defaultspack, rumi_default_tools_pack, and rumi_local_agent_pack are available.

Setup metadata lives at `ecosystem/setup_pack/rumi_data_analysis_pack/pack.json`.

## Develop

When changing this pack:

- Keep changes under `ecosystem/rumi_data_analysis_pack/` and `ecosystem/setup_pack/rumi_data_analysis_pack/pack.json`.
- Keep the pack declarative; do not add executable notebooks, Python scripts, SQL runners, routes, handlers, or functions.
- Keep network default as `none`.
- Reference underlying runtime tools by capability name instead of copying manifests.
- Use `rumi_data_analysis.*` profile ids and preset ids to avoid alias collisions.
- Treat `rumi_workspace_pack` as an optional final-artifact handoff target, not a dependency.

## Test

Run the focused contract test:

```bash
python -m pytest tobkiri_runtime/tests/test_rumi_data_analysis_pack_contract.py
```

Manual checks:

- JSON files parse.
- YAML files parse.
- Required docs exist.
- PackSelector discovers setup metadata and dependencies.
- No secret-looking literals are present.
- Overlap and defaultspack promotion metadata remain explicit.

## Common Breakages

- A preset references a missing profile or prompt.
- A chart spec omits data grain, encoding, or accessibility notes.
- A recipe describes irreversible cleaning without recording original values.
- Setup metadata adds `rumi_workspace_pack` as a hard dependency before that pack exists on the base branch.
- A copied example includes real database credentials or private paths.

## Review Checklist

- Analysis pack owns method, recipes, charts, and audit trail.
- Workspace pack owns final office artifacts.
- Network remains none by default.
- No executable code was added.
- Examples use local, placeholder-safe file names.
- Tests cover parsing, discoverability, docs, metadata, and secret scanning.
