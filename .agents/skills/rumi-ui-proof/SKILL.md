---
name: rumi-ui-proof
description: Render Rumi UI candidates or composed pages, run hard gates and compression inspection, and write proof reports with node ids and source locations.
---

You own proof, not repair.

Editable scope:
- `.rumi/ui/renders/**`
- `.rumi/ui/reports/**`

Never edit:
- source UI implementation
- foundation tokens
- candidate bundles
- accepted bundles

Required checks:
- hard gates: primary truncation, hidden primary action, horizontal overflow, unreadable control labels, action budget, padding violations, density mismatch
- compression score: gap, text, action, boundary, surface, hierarchy
- responsive stress at 390, 768, 1024, and 1440px
- text scales 1, 1.25, and 2
- scenarios default, long, empty, loading, and error
- color token usage, contrast, status color misuse, and color-only state
- grayscale hierarchy survival

Reports must include:
- node id
- candidate id
- viewport and scenario
- hard violations
- compression sub-scores
- screenshot paths
- `data-rumi-source` locations when available
