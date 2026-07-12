---
name: rumi-ui-page-composer
description: Compose Rumi recursive UI pages from accepted foundation and leaf bundles. Use when assembling a page frame, importing accepted bundles from .rumi/ui runs, wiring slots, adapters, and shell state, and enforcing that page composition never edits leaf internals.
---

# Rumi UI Page Composer

Use this skill to assemble a page from accepted Rumi UI bundles after candidate judging is complete.

## Required Rule

The page composer imports accepted bundles and does not edit leaf internals. Treat every accepted leaf as a black box with a public API. If a leaf needs visual or behavioral changes, send it back through leaf generation and judging.

## Workflow

1. Read `references/page-composition.md`.
2. Load the committed plan blueprint and contracts from `.rumi/ui/runs/{runId}`.
3. Load only accepted bundles from `.rumi/ui/runs/{runId}/accepted/{nodeId}.json`.
4. Import the accepted foundation token bundle before page or leaf rendering.
5. Compose `component-with-slots` nodes by their `slotMappings`; every required slot must receive the accepted child bundle named by the contract.
6. Add only page-level wiring: data adapters, shell state, route boundaries, slot placement, suspense/error boundaries, and cross-leaf coordination explicitly owned by the page contract.
7. Verify required scenarios, viewports, text scales, no horizontal overflow, no primary truncation, and no unaccepted candidate imports.

## Boundaries

Do not patch leaf CSS, JSX, props, state machines, generated assets, or candidate manifests from the composer. Do not copy leaf code into the page. Do not invent arbitrary design tokens locally.
