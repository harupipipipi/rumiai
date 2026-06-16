# Operations

## Install

Install this as an optional setup pack after defaultspack, rumi_default_tools_pack, and rumi_local_agent_pack are available.

The setup metadata is in `ecosystem/setup_pack/rumi_agent_services_pack/pack.json`.

## Develop

When changing this pack:

- Keep files under `ecosystem/rumi_agent_services_pack/` and setup metadata under `ecosystem/setup_pack/rumi_agent_services_pack/`.
- Keep the pack declarative unless the pack responsibility is explicitly changed.
- Add new roles as profiles and prompt contracts before adding presets that reference them.
- Reference underlying tools by capability name. Do not copy tool manifests from defaultspack or rumi_default_tools_pack.
- Keep network and write actions approval-gated in profiles and presets.

## Test

Run the pack contract test:

```bash
python -m pytest rumi_ai_1_10/tests/test_rumi_agent_services_pack_contract.py
```

Useful manual checks:

- `ecosystem.json` and setup `pack.json` parse as JSON.
- Every YAML file parses.
- Required docs from the pack documentation contract exist.
- No secret-looking keys or placeholder credentials are present.
- Setup dependencies include defaultspack, rumi_default_tools_pack, and rumi_local_agent_pack.

## Common Breakages

- A preset references a missing profile or prompt.
- A profile enables network by default.
- Setup metadata omits one of the underlying packs.
- A workflow spec starts to describe executable handler names that do not exist.
- A copied example accidentally includes a real account, token, or remote credential.

## Review Checklist

- The pack remains optional and low risk.
- No runtime core behavior is duplicated.
- Handoff contracts include evidence, approval needs, and uncertainty.
- Coding presets mention diff review, scoped edits, and tests.
- Research presets distinguish source collection from synthesis.
