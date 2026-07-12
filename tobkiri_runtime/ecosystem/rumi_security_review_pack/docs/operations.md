# Operations

## Installation

Install through the setup-pack selector as `rumi_security_review_pack`. The setup metadata marks the pack as optional and not eligible for automatic all-ok grants.

Expected prerequisite:

- `defaultspack >=2.0.0`

Optional companion packs may provide review targets, but they are not required:

- MCP gateway or MCP-related packs.
- Browser companion or browser automation packs.
- Default tool catalog packs.

## Development

Keep the pack declarative. New executable scanners, network clients, browser automation, MCP connector code, functions, routes, handlers, stores, or CI integrations are outside this pack's current scope.

When changing review behavior, update the matching files:

- `catalog/review_controls.yaml` for control coverage.
- `catalog/risk_taxonomy.yaml` for severity and evidence expectations.
- `catalog/finding_schema.json` for output record shape.
- `profiles/` for review posture.
- `prompts/` for reviewer behavior.
- `presets/` for named workflows.
- `examples/` for sample review records.

## Tests

Run the focused contract test:

```bash
python -m pytest tobkiri_runtime/tests/test_rumi_security_review_pack_contract.py
```

## Common Failure Modes

- The pack starts to enforce grants rather than reviewing them. Enforcement belongs to defaultspack and runtime policy.
- A catalog entry adds executable commands or remote scan endpoints. Keep this pack local metadata only.
- The setup metadata becomes all-ok eligible. Security review should remain opt-in and should not grant execution powers.
- MCP or browser review text implies routing ownership. MCP and browser owner packs keep routing and execution control.
- Finding examples include real credentials or sensitive operational details.

## Change Review Checklist

- Required docs from `tobkiri_runtime/docs/pack-documentation-contract.md` still exist.
- JSON and YAML assets parse.
- No executable code was added.
- No secrets or credential-like literals were added.
- Network remains none by default.
- Overlap with defaultspack, MCP gateway, and browser packs remains review-only.
