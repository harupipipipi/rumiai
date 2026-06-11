# Operations

## Review Workflow

1. Confirm the evidence already exists locally and is inside the requested scope.
2. Normalize each source into the trace record schema.
3. Apply the redaction policy before deriving any reusable procedure.
4. Match evidence against the SOP pattern catalog.
5. Draft a runbook, checklist, or workflow recipe with trace references.
6. Complete the SOP mining checklist.
7. Record approval, rejection, or revision in the ledger.
8. Promote only human-approved recipes.

## Development

The pack is asset-only. Changes should update the relevant catalog, schema, policy, template, docs, and contract test together.

## Testing

Run the focused contract:

```bash
python -m pytest tests/test_rumi_sop_mining_pack_contract.py -v
```

## Common Failure Modes

- Raw secrets or tokens appear in examples or docs.
- A recipe implies that this pack can execute automation.
- A trace source lacks consent basis or redaction status.
- A promoted SOP has no human approval record.
- A handoff surface is documented without naming the owner pack.

## Required Secrets

None.
