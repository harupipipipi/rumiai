# Architecture

## Responsibility

`rumi_security_review_pack` packages local review material for Rumi security and privacy work. Its responsibility is to guide humans and agents through threat modeling, secret scanning review, permission and grant review, MCP and browser risk review, dependency review, and release security signoff.

## Non-Responsibility

The pack does not implement scanners, permission enforcement, grant mutation, approval decisions, browser automation, MCP connection, dependency fetching, network calls, routes, handlers, stores, or executable tools. Those concerns remain owned by the runtime, defaultspack, and specialized packs.

## Directory Layout

- `ecosystem.json`: pack identity, vocabulary, local-only metadata, and asset index.
- `catalog/review_controls.yaml`: review controls and evidence expectations.
- `catalog/risk_taxonomy.yaml`: Rumi-native risk categories and default severity.
- `catalog/finding_schema.json`: local finding record schema for review output.
- `profiles/`: security reviewer profile metadata.
- `prompts/`: review prompts for threat modeling and signoff work.
- `presets/`: named review workflows.
- `examples/`: example review records.
- `docs/`: pack-specific documentation required by the documentation contract.

## Execution Path

1. A user selects the pack through setup-pack metadata.
2. A review surface reads the profile, preset, catalog, and prompt assets.
3. The reviewer inspects local code, manifests, docs, and policy metadata using existing approved tools.
4. Findings are written as local review records or release signoff notes.
5. Any grant, approval, MCP, browser, network, or dependency action remains subject to the owning runtime policy.

## Runtime Contact Points

- Complements defaultspack permission grants, approval flows, audit policy, and tool manifests.
- References MCP gateway-style review for unsupported MCP servers, but does not connect MCP servers.
- References browser risk review for browser companion or browser automation packs, but does not run browser tools.
- Can be used alongside default tools for file reading or local search only when those tools are already available and approved.

No pack-owned Python modules are imported during normal use.
