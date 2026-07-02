# Tag-based Requirements

Marketplace cards can declare prerequisites for packs, skills, tools, MCP surfaces, models, and future extension kinds. Requirements use human-readable tags instead of UUIDs or another opaque selector.

## Tag rules

- Tags are free-form strings. A publisher may introduce a tag without registering a central numeric ID.
- Broad and specific tags can coexist: `coding`, `coding.python`, and `coding.python.refactor`.
- UUID-shaped strings are rejected as selectors. `card_id` remains a stable provenance key, not a dependency selector.
- Matching implementations should trim surrounding whitespace, apply Unicode normalization, and compare tags case-insensitively.
- Dots, hyphens, and slashes remain meaningful. They can be used to organize a vocabulary without making it closed.
- A card should publish both discovery tags and compatibility tags when they differ.

## Requirement selectors

Top-level requirement entries are combined with AND. Each entry selects either any or all of its tags.

```yaml
requirements:
  - kind: pack
    selector:
      match: any
      tags: [coding.workspace, coding.ide]
    prefer_pack: true
    marketplace_fallback: search
  - kind: mcp_tool
    selector:
      match: any
      tags: [mcp.github.repository, mcp.git.repository]
    stage: runtime
  - kind: extension
    required: false
    selector:
      match: all
      tags: [extension.review, extension.markdown]
```

The example means:

1. A pack matching `coding.workspace` **or** `coding.ide` is required.
2. An approved MCP tool matching either repository tag is also required.
3. A review extension must provide both extension tags when present, but the extension is optional.

`kind` is intentionally an open namespace. The well-known values are `pack`, `skill`, `tool`, `mcp_tool`, `mcp_server`, `model`, and `extension`; a namespaced third-party kind can be added without changing a central enum.

## Pack-first resolution

`prefer_pack` defaults to true. A resolver should use this order:

1. An installed and approved pack whose provided tags satisfy the selector.
2. A matching skill, tool, MCP descriptor, or extension supplied by an installed pack.
3. A reviewed local standalone candidate.
4. Marketplace discovery when `marketplace_fallback` is `search` or `prompt_install`.

Marketplace discovery is only a proposal. It must not auto-install a candidate, connect an MCP server, grant permissions, or accept credentials. Existing install review, provenance, trust, and explicit approval rules still apply.

## Model tiers

Cards may request a provider-independent model tier and additional model capability tags. The concrete model remains a defaultspack routing decision.

| Tier | Intended use |
| --- | --- |
| `rough` | Low-risk, replaceable bulk work such as tag normalization, search drafting, and first-pass summaries. |
| `standard` | Normal chat, routine tools, document work, and reversible workflows. |
| `strong` | Coding, complex planning, multi-step tool use, and review assistance. |
| `frontier` | Difficult reasoning, adversarial review, and high-complexity final review. |

`rough_use_allowed: true` never overrides safety or approval policy. High-impact decisions, destructive actions, trust decisions, and final regulated-domain output require stronger handling.

## Marketplace preview

Listing status supports `private`, `preview`, `coming_soon`, `listed`, and `delisted`. Until remote discovery and install handoff are implemented, the UI should show:

- `Marketplace`
- `Coming soon`
- a visible but disabled `探す` button

This keeps the user-facing route stable while making it clear that search does not yet fetch or install remote content.
