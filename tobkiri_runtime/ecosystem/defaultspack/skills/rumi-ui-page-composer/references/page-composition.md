# Page Composition Rules

## Accepted Bundle Imports

Import only bundles that the judge accepted for the same `runId` and `nodeId`. A page must not import:

- Candidate directories.
- Rejected candidates.
- Previous-run accepted bundles unless the plan explicitly pins them.
- Leaf source files by private path.
- Local design-value files that bypass the accepted foundation.

## Slot Composition

For each `component-with-slots` contract:

- Use `slotMappings` as the source of truth.
- Preserve child order only when the contract or perceptual task requires it.
- Respect each slot's `minWidth`, `preferredWidth`, `maxWidth`, and `required` flag.
- Fail closed when a required slot has no accepted child.

## Composer Responsibilities

The composer may own:

- Page route boundaries and shell placement.
- Data fetching/adaptation when the page contract owns it.
- Cross-leaf state that is explicitly assigned to the page/frame.
- Error, loading, and suspense boundaries around accepted leaves.
- Responsive arrangement between accepted leaves.

The composer must not own:

- Leaf-local controls, mutations, or states.
- Leaf visual token choices.
- Internal leaf responsive algorithms.
- Private leaf files or generated implementation details.

## Verification

Before acceptance, verify the composed page at all required viewports and text scales, using default, long, empty, loading, and error scenarios. Reject composition that hides a required leaf, overflows horizontally, truncates primary content, overlaps controls, or imports unaccepted code.
