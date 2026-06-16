# Operations

Use `rumi_observability_pack` when the requested work fits its owner surfaces: agent_run_ledgers, tool_call_evidence, cost_latency_summaries, postmortem_templates. Start by collecting enough evidence, then route any overlapping execution to the owner pack named in setup metadata. Do not treat a generated plan as completed work until the relevant evidence proves the requested outcome.

## Review Flow

1. Classify the request as event review, run-ledger review, cost/latency review, incident review, or postmortem drafting.
2. Confirm the relevant asset contract: event schema, run ledger contract, redaction policy, incident checklist, or postmortem template.
3. Verify required fields and evidence references before writing a summary.
4. Apply `privacy_cost_redaction.policy.yaml` before any handoff outside the local review context.
5. Route overlapping action to the owner pack: model scoring to `rumi_model_evals_pack`, release remediation to `rumi_devops_release_pack`, security analysis to `rumi_security_review_pack`, and agent-service runtime changes to `rumi_agent_services_pack`.

## Focused Verification

- Parse every JSON and YAML asset.
- Run `validate_ecosystem` against `ecosystem.json`.
- Confirm `metadata.asset_index` names every shipped pack asset.
- Confirm setup metadata remains marketplace-verified, signing-verified, `supports_all_ok: false`, and defaultspack promotion disabled.
- Reject generic placeholder examples and secret-like payloads.

## Common Failure Modes

- A ledger has cost or latency values without units.
- An incident report links no trigger event.
- A postmortem includes raw connector payloads or private prompt text.
- A handoff names a target pack without the evidence required by `handoff_review.preset.yaml`.
