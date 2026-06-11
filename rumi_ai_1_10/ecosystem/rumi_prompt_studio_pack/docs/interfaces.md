# Interfaces

Prompt Studio exposes file-level contracts rather than runtime interfaces.

## Prompt Artifact Interface

`schemas/prompt_artifact.schema.json` describes a reusable prompt asset with:

- Stable `id`.
- `audience` and `objective`.
- `instruction_hierarchy`.
- Slot definitions.
- Style preset references.
- Lint rubric references.
- Local dry-run fixture references.
- Explicit owner and handoff fields.

## Migration Interface

`schemas/instruction_migration_record.schema.json` describes how instructions from Claude, ChatGPT, or Gemini are translated into Rumi fields. Migration records must separate:

- Portable behavior.
- Platform-specific behavior.
- Blocked imports.
- Clarifying questions.
- Reviewer notes.

## Review Interface

`schemas/prompt_lint_result.schema.json` and `templates/prompt_review_report.template.yaml` define the review output. Reviewers must capture evidence for instruction hierarchy, style clarity, testability, privacy, migration fidelity, and boundary ownership.

## Handoff Points

Handoff is required when an artifact requests model routing, model scoring, persistent memory, tool creation, API creation, remote execution, or production telemetry. The Prompt Studio Pack records the handoff and blocks release until the owning pack is named.
