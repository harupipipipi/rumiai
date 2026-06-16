# Interfaces

## Inputs

- `goal`: The browser task to complete.
- `target_url`: Optional URL or currently active tab.
- `state_constraints`: Login, account, environment, or tenant constraints.
- `allowed_actions`: The action verbs allowed for this run.
- `stop_conditions`: Conditions that require pausing or asking for review.

## Outputs

- `plan`: Step list with observation and action phases.
- `evidence_ledger`: Screenshots, semantic node references, visible text, and action results.
- `completion_state`: done, blocked, needs_review, or unsafe.
- `handoff`: Compact summary for agent services or workspace artifacts.

## Required Secrets

None. The pack references no API keys, passwords, or tokens.
