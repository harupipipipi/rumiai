# Operations

## Start

Select `rumi_memory_knowledge_pack` through the setup pack selector. The selector entry is `ecosystem/setup_pack/rumi_memory_knowledge_pack/pack.json`.

There is no service to start. This pack is data-only.

## Develop

When changing this pack:

1. Keep executable code out of the pack unless the pack responsibility changes.
2. Update `ecosystem.json` when adding or moving catalog/spec/policy/profile/prompt/example directories.
3. Update `docs/interfaces.md` when capability names, stores, grants, secrets, or network posture change.
4. Keep examples synthetic and free of personal user memories.
5. Preserve the boundary that this pack does not write runtime memory.

## Test

Run the focused contract test:

```bash
cd rumi_ai_1_10
python -m pytest tests/test_rumi_memory_knowledge_pack_contract.py
```

The test verifies required docs/assets, JSON/YAML parsing, setup selector discoverability, no obvious secret-like payloads, and overlap/defaultspack promotion metadata.

## Common Failure Modes

- Missing required docs from the shared pack contract.
- Invalid JSON or YAML in catalogs, specs, policies, profiles, presets, or examples.
- Adding hard dependencies on packs that should remain optional collaborators.
- Treating declarative capability names as executable memory tools.
- Accidentally copying personal memory records into examples.

## Review Checklist

- The pack remains local-first and declarative.
- `required_secrets` is empty.
- Network posture remains `none_by_default`.
- Runtime memory write policy remains `defines_contracts_only`.
- Overlap notes cover `defaultspack`, `rumi_agent_services_pack`, `rumi_research_pack`, and `rumi_local_agent_pack`.
- Defaultspack promotion remains disabled.
