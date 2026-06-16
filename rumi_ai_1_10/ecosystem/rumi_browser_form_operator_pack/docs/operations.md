# Operations

## Review Checklist
  - Confirm the user intent belongs to Rumi Browser Form Operator Pack.
  - Check overlap policy before selecting tools.
  - Preserve evidence and validation commands.
  - Keep defaultspack promotion disabled until runtime evidence exists.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.

## Thick Review Checklist
  - Semantic DOM evidence includes selector, visible label, role/type, aria, autocomplete, required/optional, disabled/read-only, validation, and submit controls.
  - Field risk is classified as low, medium, high, or irreversible before staging values.
  - Medium-risk fields require explicit user confirmation before fill.
  - High-risk fields hand off to security review before fill.
  - Every submit records pre-submit review, submit button text, before/after screenshots, receipt state, and rollback/contact notes when visible.
