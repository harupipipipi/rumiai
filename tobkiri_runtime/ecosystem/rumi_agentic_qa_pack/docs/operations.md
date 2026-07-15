# Operations

## Review Checklist
  - Confirm the user intent belongs to Rumi Agentic QA Pack.
  - Check overlap policy before selecting tools.
  - Preserve evidence and validation commands.
  - Keep defaultspack promotion disabled until runtime evidence exists.
  - Confirm each QA lane uses scenario, adversarial, regression, evidence, and handoff subagents.
  - Apply the acceptance rubric before marking a replay as passed.
  - Record expected and actual observations in the QA evidence ledger.
  - Route browser, model scoring, security, and observability failures to their owner packs.

## Required Secrets
None. This pack is declarative and does not bundle credentials, API keys, or executable network clients.

## defaultspack Relationship
This pack depends on defaultspack and contributes routing metadata, handoff boundaries, and evidence requirements.

## Evidence
Every workflow must preserve enough evidence for a reviewer to understand the inputs, chosen handoff, and validation result.
