# Settings Information Architecture

## Core rule

Settings are grouped by the user's mental model, not by implementation folders.

Implementation categories like `tool`, `node`, `provider`, `adapter`, `pack`, and `runtime` are not automatically UI categories. Users are trying to answer:

- Which model/API am I using?
- Which accounts are connected?
- Which tools can Rumi call?
- Can Rumi control my computer?
- What happens when my computer sleeps?
- What data can Rumi access?

## Final section definitions

### Quick Setup

Setup blockers, missing API keys, missing account connections, missing OS permissions, cloud continuation status.

### Models & API

Model roles, provider API keys, routing, fallback, token policy.

### Accounts & Connections

OAuth/API-key connections: Cloudflare, Google, Gmail, Drive, GitHub, Slack, Notion, custom providers.

### Tools & MCP

Tool providers, MCP servers, discovered tool list, tool enable/disable, tool approval policy.

### Computer & Automation

Screen observation, clicking/typing/scrolling, browser automation, cloud continuation, checkpoint/resume, local permissions.

### Workspace & UI

Theme, layout, panes, right bar, input behavior, shortcuts, visual indicators.

### Profiles

Profile-specific model/tool/connection/policy/node state.

### Privacy & Security

Credential storage, audit logs, approvals, data retention, cloud/local boundaries.

### Packs & Extensions

Pack lifecycle, extension settings contributions, pack-specific configuration.

### Advanced

Rare power-user settings.

### Diagnostics

Logs, health checks, debug JSON, migration diagnostics.

## Sorting rule

1. Setup blockers.
2. Frequently changed settings.
3. User-visible capabilities.
4. Active profile settings.
5. Rare settings.
6. Developer/debug settings.

## Prohibited UI leaks

- Raw ids as primary labels: `mimo`, `openrouter_auto`, `computer_use_gradient`, `defaultspack.agent`.
- Debug flags in normal-user top-level.
- Visual-only settings above functional settings.
- MCP server and OAuth account represented as the same thing.
