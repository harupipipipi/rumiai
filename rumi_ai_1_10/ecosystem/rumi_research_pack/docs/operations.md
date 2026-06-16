# Operations

## Start

Select `rumi_research_pack` through the setup pack selector. The selector metadata lives at `ecosystem/setup_pack/rumi_research_pack/pack.json`.

There is no service to start. This pack is data-only.

## Develop

When changing this pack:

1. Keep executable code out of the pack unless its responsibility changes.
2. Update `ecosystem.json` when adding or moving declared directories.
3. Update `docs/interfaces.md` when capability names, grants, stores, secrets, or network posture change.
4. Keep examples synthetic and free of private data.
5. Keep `network_policy` as `none_by_default` unless a future PR intentionally changes the pack boundary.

## Test

Run the focused contract test:

```bash
cd rumi_ai_1_10
python -m pytest tests/test_rumi_research_pack_contract.py
```

The test verifies required docs/assets, JSON/YAML parsing, setup selector discoverability, overlap/defaultspack promotion metadata, and obvious secret-like payloads.

## Common Failure Modes

- Missing required docs from the shared pack documentation contract.
- Invalid JSON or YAML in catalog files.
- Adding hard runtime dependencies for functionality that should remain optional.
- Treating catalog capability names as executable tools before a tool pack implements them.
- Accidentally embedding copied private source data or credentials in examples.

## Review Checklist

- The pack remains declarative and local-first.
- `required_secrets` is empty.
- Network posture remains `none_by_default`.
- Setup metadata documents overlap with `defaultspack`, `rumi_workspace_pack`, and `rumi_agent_services_pack`.
- Defaultspack promotion is explicitly disabled.
- Tests parse all catalog/profile/preset/example YAML and all JSON.
