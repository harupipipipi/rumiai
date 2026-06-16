# Interfaces

## Inputs

- `media_source`: Local file, screenshot, asset reference, transcript, or storyboard.
- `task_type`: understand, extract, generate_brief, review, compare, or handoff.
- `rights_context`: Ownership, license, consent, or usage limits.
- `privacy_context`: Personal data, credentials, faces, locations, or sensitive UI state.

## Outputs

- `asset_ledger`: Source, transformations, rights notes, and approved uses.
- `media_findings`: OCR text, visual layout, accessibility notes, defects, or transcript summary.
- `generation_brief`: Prompt, constraints, dimensions, references, and review rubric.
- `handoff`: Workspace-ready or browser-QA-ready artifact summary.

## Required Secrets

None.
