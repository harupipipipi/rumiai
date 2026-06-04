# Rumi Knowledge Marketplace Pack

Rumi Knowledge Marketplace Pack defines how Rumi should catalogue reusable skills, templates, playbooks, connector cards, and install candidates. It borrows from OpenClaw skills and Hermes skills, but treats marketplace content as untrusted until reviewed.

## Included Assets

- `schemas/marketplace_card.schema.json` defines card IDs, capability types, publishers, permission summaries, provenance, trust status, and install review.
- `catalog/trust_rubric.yaml` defines unreviewed, repository-reviewed, trusted, and blocked states.
- `workflows/install_review_workflow.yaml` defines local-first review phases and explicit approval requirements.
- `ledgers/provenance_ledger.yaml` defines the digest, reviewer, status, permission, and blacklist evidence needed for each candidate.
- `policies/promotion_blacklist.policy.yaml` defines promotion requirements, blockers, blacklist reasons, and recheck rules.

## Required Secrets

None.

## Network

None by default. Marketplace cards may describe connector or remote capabilities, but this pack does not fetch candidates, install content, or grant connector access.

## Overlap Policy

This pack is intentionally declarative. `defaultspack` owns grants, active pack selection, and runtime enforcement. Related packs own their execution surfaces. This pack contributes policies, profiles, prompts, presets, examples, and handoff contracts for its own surface.
