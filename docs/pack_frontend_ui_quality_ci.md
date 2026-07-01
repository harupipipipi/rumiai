# Pack frontend UI quality CI

This CI is a Rumi AI pack UI gate. It is not defaultspack-only. The defaultspack webapp is currently used as the host harness because pack commands, sidecars, renderers, composer effects, and activity previews are mounted there today.

## Applies to

Use this gate for any pack that adds frontend-facing command manifests, sidecar surfaces, renderer manifests, composer effects, timeline views, preview panes, or editor panes.

## Blocking checks

The Playwright contract should fail when a pack UI breaks shell layout or basic interaction. Required checks include:

- chat pane keeps a readable width when a sidecar opens
- long message bubbles do not collapse into narrow vertical strips
- chat and sidecar panes do not unexpectedly overlap
- primary panes stay inside the viewport
- slash command entry opens the requested surface
- toolbar buttons, editable fields, Composer append, and close actions are operable
- browser console and page errors remain clean during the flow

## Warning checks

Non-blocking warnings should be captured as artifacts or audit output for near-limit density, suspicious placeholder content, weak text pressure margins, or UI that is visible but not wired to real operations yet.

## Pack author rule

When a pack adds a frontend UI command or renderer, add a fixture to `rumi_ai_1_10/ecosystem/defaultspack/webapp/e2e/pack-ui-layout-contract.spec.ts` or to the shared pack UI fixture that replaces it. The fixture should model the command manifest, command execution response, surface descriptor, and at least one real operation path.

## Future home

The recursive frontend precision work in PR378 is the right long-term home for the reusable audit rules. The immediate CI gate lives in the web host so pack-surface PRs are blocked before merge.
