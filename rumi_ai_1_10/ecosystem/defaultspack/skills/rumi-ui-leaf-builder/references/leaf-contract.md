# Leaf Contract Rules

## Zero-From-Empty-Directory Generation

Every candidate must be generated into a new empty directory. The directory may receive contract input and token imports, but it must not begin with copied code from:

- Another candidate.
- A previous failed version of the same candidate.
- A page composer.
- A different leaf.
- The defaultspack webapp shell.

Allowed carry-over from a failed candidate is limited to judge findings, screenshots, and written notes. Reuse the lesson, not the files.

## Contract Coverage

Implement the contract exactly:

- `purpose` and `primaryPerceptualTask` drive visual hierarchy.
- `density` sets spacing and information density through tokens.
- `layoutEnvelope` sets min, preferred, max width and height/mobile behavior.
- `responsibilities` define the visual roles, controls, mutations, states, layout algorithms, and responsive topologies the leaf must own.
- `ownership` keeps related inputs, events, mutations, and states in one internal boundary.
- `inputs`, `events`, and `requiredStates` define the public API and scenarios.
- `allowedPrimitives` limits component choices.
- `visibleActionBudget` caps visible actions.

Do not merge, rename, or drop contract obligations to simplify the implementation.

## Token Use

Use only accepted foundation tokens for design values. Hard-coded numeric layout may be used only for structural calculations that are not design tokens, such as derived grid counts from container width. When in doubt, promote the value to foundation review instead of hiding it in the leaf.

## Candidate Manifest Minimum

Include:

- `runId`, `nodeId`, `candidateId`, `contractPath`, and `foundationRef`.
- Entry files and exported public component/API.
- Scenario coverage for default, long, empty, loading, and error unless the plan config says otherwise.
- Viewport and text-scale coverage.
- Known limitations, which must be empty for acceptance.
