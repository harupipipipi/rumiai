# Operations

Use this pack as a review surface before prompt artifacts are copied into a runtime or product pack.

## Review Flow

1. Select a prompt from `catalog/prompt_library.yaml` or draft a new artifact using `schemas/prompt_artifact.schema.json`.
2. Apply the matching rubric in `catalog/prompt_lint_rubrics.yaml`.
3. Check migration provenance when the prompt came from Claude, ChatGPT, or Gemini instructions.
4. Run the local fixture mentally or in an external owner-approved harness.
5. Fill the ledger using `ledgers/prompt_studio_review_ledger.schema.yaml`.
6. Complete `checklists/prompt_release.checklist.yaml`.

## Required Evidence

- Prompt artifact id and version.
- Rubric ids used.
- Fixture ids used.
- Expected response traits.
- Actual observed response summary when a runtime owner runs it.
- Boundary handoffs for any requested runtime, model, memory, tool, or API behavior.

## Required Secrets

None.

## Safety Notes

Do not paste real customer data into fixtures. Do not store persistent personal preferences in presets. Do not turn platform-specific instructions into hidden memory. Do not use local fixture dry runs as benchmark claims.
