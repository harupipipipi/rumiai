# Operations

## Start

Install or select the pack through the setup pack selector. The selector entry lives at `ecosystem/setup_pack/rumi_workspace_pack/pack.json`.

Because the pack is declarative, there is no service to start.

## Develop

When changing this pack:

1. Keep executable code out unless the pack responsibility changes.
2. Update `ecosystem.json` when adding new catalog, profile, preset, prompt, or example directories.
3. Update `docs/interfaces.md` when any interface, grant, store, secret, or network expectation changes.
4. Keep catalogs implementation-neutral so multiple tool packs can satisfy them.
5. Do not place credentials, service endpoints with private tokens, or environment-specific data in examples.

## Test

Run the focused contract test:

```bash
cd tobkiri_runtime
python -m pytest tests/test_rumi_workspace_pack_contract.py
```

The test checks required docs, JSON validity, setup selector visibility, dependency metadata, and obvious secret-like payloads.

## Common Failure Modes

- Missing required docs after adding or moving the pack.
- Invalid JSON in `ecosystem.json`, setup metadata, or catalog JSON.
- Adding a hard dependency under `depends_on` without updating setup-pack validation expectations.
- Treating catalog entries as executable tools before a runtime pack implements them.
- Accidental inclusion of credentials in examples copied from a real workspace.

## Review Checklist

- The pack remains optional and declarative.
- Required docs still match the documentation contract.
- `required_secrets` is empty.
- Network posture remains `none_by_default`.
- Setup metadata includes dependencies and harmless conflict metadata.
- Profiles, presets, prompts, examples, and catalogs all reference workspace artifact work explicitly.
