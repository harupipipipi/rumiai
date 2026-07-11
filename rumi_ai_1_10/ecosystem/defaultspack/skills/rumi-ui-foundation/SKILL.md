---
name: rumi-ui-foundation
description: Create or review Rumi recursive UI foundation bundles for design-token governance. Use when defining accepted foundation tokens for Rumi UI leaves and pages, normalizing token names, checking token-only compliance, or preparing the foundation that leaf builders and page composers must consume.
---

# Rumi UI Foundation

Use this skill to produce the accepted foundation for a Rumi UI run. The foundation is the only source of design values for generated leaves and composed pages.

## Workflow

1. Read `references/token-rules.md` before creating or accepting a foundation bundle.
2. Derive a small semantic token set from the product need and target density.
3. Keep the bundle token-only. Do not include components, page structure, copy, data, routes, or interaction logic.
4. Name tokens by role, not current color or pixel value: `surface.panel`, `text.muted`, `space.control-gap`, `radius.control`.
5. Reject arbitrary leaf-local values once an accepted foundation exists. Leaves and pages must import tokens instead of inventing colors, spacing, radii, shadows, typography, motion, or breakpoints.
6. Keep local-first behavior. Do not require network, cloud keys, external fonts, or remote assets.

## Accepted Output

An accepted foundation bundle may contain token definitions, CSS variables or equivalent exports, and concise provenance. It must not contain React components, DOM markup, layout implementation, generated leaf code, page composition code, or runtime data adapters.

If a requested UI cannot be expressed with the current tokens, revise the foundation first and re-judge dependent candidates.
