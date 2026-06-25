# Rumi Recursive UI Compiler Packages

These packages implement the first executable slice of Rumi's recursive UI compiler:

- `rumi-ui-contracts`: shared schemas, config, and validation for UI nodes, foundations, component contracts, and design intent.
- `rumi-ui-planner`: complexity scoring, recursive leaf splitting, leaf budget checks, and candidate count planning.
- `rumi-ui-orchestrator`: role-scoped write policies, candidate task creation, artifact storage, and regenerate-instead-of-patch flow control.
- `rumi-ui-renderer`: render matrix and specimen manifests for browser-backed verification.
- `rumi-ui-inspector`: compression, color-token, and hard-gate inspection from rendered evidence.
- `rumi-ui-selector`: tournament selection and retry/re-split decisions.

The packages are dependency-free ESM modules so they can be exercised without installing a new root toolchain:

```bash
npm run test:ui-compiler
```
