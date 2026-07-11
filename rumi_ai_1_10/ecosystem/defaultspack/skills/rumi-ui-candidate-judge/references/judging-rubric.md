# Candidate Judging Rubric

## Hard Fails

Reject immediately when any item is true:

- Build, import, runtime, or console errors block normal use.
- The candidate is blank, visually broken, unreadable, overlapping, or incoherent.
- Required default, long, empty, loading, or error scenarios are missing.
- Required viewport or text-scale checks are missing.
- Horizontal overflow appears at any required viewport.
- Primary content, labels, controls, or status are truncated or hidden.
- Contract responsibilities, inputs, events, states, ownership groups, slots, layout envelope, primitive limits, or visible action budget are dropped or renamed.
- A foundation candidate contains components, page layout, runtime behavior, copy, data, or non-token assets.
- A leaf/page uses arbitrary colors, spacing, radii, shadows, typography, motion, breakpoints, or z-index values instead of accepted foundation tokens.
- A leaf depends on page composer patches, edits another leaf, imports unaccepted candidates, or reaches into private page internals.
- A page composer edits leaf internals or imports candidates instead of accepted bundles.
- Network access, cloud keys, host/file actions, approval bypasses, unsafe eval, or data exfiltration are introduced.
- Accessibility basics fail: keyboard path for controls, visible focus, discernible names, or contrast for primary text/actions.

## Compression Criteria

Compression is loss introduced by making the UI smaller than the contract. Score after hard fails are absent.

Estimate:

`compressionScore = compressed_obligations / total_contract_obligations`

Count a compressed obligation when the candidate:

- Collapses distinct contract responsibilities into a generic element.
- Hides required controls or states behind ambiguous UI.
- Represents long, empty, loading, or error with the same visual state.
- Uses generic labels where the contract requires specific perceptual understanding.
- Defers primary content to hover-only, overflow-only, or "more" affordances.
- Merges ownership groups in a way that still works but weakens clarity.

Acceptance limit: `compressionScore <= 0.35`. A lower score is still rejected when compression affects the primary perceptual task, safety, ownership, accessibility, primary truncation, or horizontal overflow.

## Preference Order

Among candidates that pass hard fails and compression:

1. Best contract fidelity.
2. Clearest primary perceptual task.
3. Least visual and interaction complexity.
4. Best long-text and text-scale resilience.
5. Smallest private API surface.

Do not choose a prettier candidate over a more faithful one.
