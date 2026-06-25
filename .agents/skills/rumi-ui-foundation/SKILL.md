---
name: rumi-ui-foundation
description: Propose one complete Rumi UI foundation candidate from zero, including tokens, primitives, specimen pages, and gallery proof inputs.
---

You own one foundation candidate only.

Editable scope:
- `.rumi/ui/foundation/<candidate>/**`
- `src/ui/primitives/**`
- `src/ui/tokens/**`

Never edit:
- page routes
- page composition
- leaf candidate directories
- accepted bundles

Required outputs:
1. `foundation.json` with direction, typography scale, font family, weights, line heights, colors, semantic color roles, spacing, density profiles, radius, borders, shadows, layout grid, icon policy, and motion policy.
2. `tokens.css` or equivalent token artifact using only semantic token names.
3. primitive controls for the allowed primitive set.
4. a type specimen page or story.
5. a color specimen page or story.
6. a primitive gallery page or story.
7. `foundation-proof.json` listing the required render jobs.

Type specimen requirements:
- Render at 390, 768, and 1440px.
- Include long Japanese headings, Japanese and alphanumeric mixed strings, long company names, dates and money, tables, form labels, message body text, buttons, captions, and errors.
- Verify Japanese line breaks, heading mass, body readability, numeric alignment, lowercase legibility, visible weight differences, and dense UI readability.

Foundation rules:
- Do not make a decorative-first or toy-like direction for utility UI.
- Do not solve fit by making text smaller than the foundation type role.
- Do not introduce one-off hex colors outside foundation tokens.
- Do not rely on color alone to encode state.
- Do not create leaf-specific layout decisions.
