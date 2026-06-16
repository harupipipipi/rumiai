# Rumi Security Review Pack

`rumi_security_review_pack` is an optional, declarative, local-first pack for Rumi-native security and privacy review. It provides review catalogs, profiles, prompts, presets, examples, and signoff templates for threat modeling, secret scanning, permission review, MCP and browser risk, dependency review, and release security signoff.

## What It Provides

- Security and privacy review checklists for Rumi packs, tools, prompts, MCP connectors, browser surfaces, and release changes.
- Risk taxonomy metadata for secrets, permissions, grants, network, filesystem, browser automation, MCP tools, dependencies, and release readiness.
- Local-first review profiles and presets for design review, implementation review, release signoff, and incident follow-up.
- Rumi-native prompts that complement defaultspack approvals and grants without overriding them.
- Example review records and finding schemas that can be copied into local docs or issue trackers.

## What It Does Not Provide

- No executable scanners, network clients, dependency downloaders, browser automation, MCP connector code, or CI integration.
- No changes to defaultspack permission grants, approval decisions, tool execution, or MCP/browser routing.
- No secrets, credentials, API keys, private tokens, or remote service configuration.
- No automatic pass/fail authority over a release; it produces review guidance and signoff metadata only.

## Docs

Start with [docs/README.md](docs/README.md), then read [docs/architecture.md](docs/architecture.md), [docs/interfaces.md](docs/interfaces.md), and [docs/operations.md](docs/operations.md).
