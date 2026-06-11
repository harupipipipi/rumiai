# Architecture

Rumi Prompt Studio Pack is a content and contract pack. Its architecture is intentionally flat: catalogs describe prompt artifacts, schemas define portable record shapes, policies define review rules, fixtures provide local inputs, and ledgers record evidence.

## Ownership

Prompt Studio owns:

- Prompt library entries.
- Prompt linting rubrics.
- Persona/style presets.
- Custom instruction migration maps.
- Local fixture dry-run declarations.
- Prompt review report templates and ledgers.

Prompt Studio hands off:

- Runtime execution to `defaultspack`.
- Model scoring to a model evaluation pack.
- Model routing to the default runtime or model catalog owner.
- Memory storage and preference persistence to a memory owner.
- Tool and API creation to a tooling owner.

## Data Flow

1. A prompt artifact is drafted using `schemas/prompt_artifact.schema.json`.
2. A reviewer selects a rubric from `catalog/prompt_lint_rubrics.yaml`.
3. Fixture input is selected from `fixtures/local_dry_run_cases.yaml`.
4. Evidence is recorded using `ledgers/prompt_studio_review_ledger.schema.yaml`.
5. Release readiness is checked with `checklists/prompt_release.checklist.yaml`.

No step requires network access or bundled secrets.

## Boundary Rule

The pack may describe how a prompt should ask before using a tool, but it must not define the tool. The pack may describe how a style preset should phrase a response, but it must not store user memory. The pack may define fixture expectations, but it must not claim model performance.
