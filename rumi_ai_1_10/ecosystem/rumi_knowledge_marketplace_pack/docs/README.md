# Rumi Knowledge Marketplace Pack Docs

These docs describe the declarative contract for `rumi_knowledge_marketplace_pack`. The pack does not add executable runtime behavior; it provides pack-specific structure for planning, review, and handoff.

Read the docs in this order:

1. `architecture.md` for marketplace ownership boundaries and local-first trust review.
2. `interfaces.md` for card, provenance, install-review, secret, network, and grant contracts.
3. `operations.md` for review flow, promotion/blacklist handling, and focused verification.

Primary assets:

- Marketplace card schema: `schemas/marketplace_card.schema.json`
- Trust rubric: `catalog/trust_rubric.yaml`
- Install review workflow: `workflows/install_review_workflow.yaml`
- Provenance ledger: `ledgers/provenance_ledger.yaml`
- Promotion and blacklist policy: `policies/promotion_blacklist.policy.yaml`
