---
name: rumi-ui-leaf-builder
description: Build Rumi recursive UI leaf candidates from component contracts. Use when generating isolated leaf implementations from .rumi/ui contracts, producing multiple candidate bundles, enforcing zero-from-empty-directory generation, consuming accepted foundation tokens, and avoiding edits to page composer or other leaf internals.
---

# Rumi UI Leaf Builder

Use this skill to generate leaf candidates from a committed Rumi UI component contract.

## Inputs

- A single contract from `.rumi/ui/runs/{runId}/contracts/{nodeId}.json`.
- The accepted foundation token bundle.
- Required scenarios from the plan config, normally default, long, empty, loading, and error.
- Required viewports and text scales from the plan config.

Read `references/leaf-contract.md` before generating or regenerating a candidate.

## Workflow

1. Start each candidate from an empty candidate directory.
2. Generate only the files needed for that leaf candidate.
3. Implement every contract responsibility, input, event, state, ownership group, primitive allowance, visible action budget, and layout envelope.
4. Use accepted foundation tokens for all colors, spacing, radii, shadows, typography, motion, breakpoints, and z-index values.
5. Exercise all required scenarios, viewports, and text scales.
6. Produce a candidate manifest with contract id, candidate id, files, token imports, scenario coverage, and verification notes.

## Boundaries

Do not edit page composer files, other leaves, accepted bundles, compiler output, manifests, Python, tests, or runtime code. If a contract is impossible or ambiguous, stop with a contract issue instead of inventing behavior.

If a candidate fails hard acceptance, discard the candidate directory and regenerate from empty. Do not patch a failed directory into shape.
